"""Synthetic terms below are unit-test inputs only, never production evidence."""
from dataclasses import replace
from datetime import date,datetime,timezone
from decimal import Decimal as D
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,unittest
from automation.v101.actions import Snapshot,Entitlement,EntitlementBook,holding_coverage
from automation.v101.archive import preserve
from automation.v101.exposure_analysis import attribution,compare_exposure
from automation.v101.paired_controls import targets as matched_targets,simulate_matched
from automation.v101.research import DataBlocked,simulate,Market,targets
from automation.v101.specs import SPECS,registry
from tests.v101.test_challenger import fixture

class ReviewTests(unittest.TestCase):
    def source(self,rows=None):
        body=json.dumps(dict(stat='OK',fields=['資料日期','股票代號','名稱','前收','參考','權值+息值','權/息'],
            data=rows or [['113年02月01日','1100','TEST','10','9','1','息']])).encode()
        return Snapshot('https://www.twse.com.tw/rwd/zh/exRight/TWT49U?response=json',
            '2024-03-01T00:00:00+00:00',body,sha256(body).hexdigest())

    def event(self,kind='CASH_DIVIDEND',**kwargs):
        values=dict(event_id='UNIT_TEST_ONLY',symbol='1100',kind=kind,
            announced_at='2024-01-01T00:00:00+08:00',available_at='2024-01-01T00:01:00+08:00',
            ex_date=date(2024,2,1),settlement_date=date(2024,2,20),cash_per_share=D(2))
        values.update(kwargs);return Entitlement(**values)

    def test_reference_is_not_fabricated_dividend_or_historical_announcement(self):
        row=self.source().reference_inventory()[0]
        self.assertIsNone(row['announced_at']);self.assertIsNone(row['payment_date'])
        self.assertFalse(row['entitlement_verified']);self.assertNotIn('cash_per_share',row)

    def test_signed_rights_reference_is_preserved_not_inferred_as_cash(self):
        row=self.source([['113年02月01日','1100','TEST','10','11','-0.5','權']]).reference_inventory()[0]
        self.assertEqual(row['reference_adjustment'],'-0.5')
        self.assertFalse(row['entitlement_verified'])

    def test_bad_source_digest_and_nonofficial_host_block(self):
        for source in (replace(self.source(),digest='0'*64),replace(self.source(),url='https://twse.com.tw.evil.invalid/rwd/zh/exRight/TWT49U'),replace(self.source(),url='https://www.twse.com.tw:8443/rwd/zh/exRight/TWT49U')):
            with self.assertRaises(DataBlocked):source.reference_inventory()

    def test_reference_schema_change_and_duplicate_rows_block(self):
        source=self.source();p=json.loads(source.body);p['fields'][5]='OTHER'
        body=json.dumps(p).encode()
        with self.assertRaisesRegex(DataBlocked,'SCHEMA'):replace(source,body=body,digest=sha256(body).hexdigest()).reference_inventory()
        r=['113年02月01日','1100','TEST','10','9','1','息']
        with self.assertRaisesRegex(DataBlocked,'DUPLICATE'):self.source([r,r]).reference_inventory()

    def test_cash_entitlement_is_receivable_until_pay_date(self):
        book=EntitlementBook();e=self.event()
        book.accrue(e,1000,e.ex_date,datetime(2024,2,1,tzinfo=timezone.utc))
        self.assertEqual(book.receivable(date(2024,2,2)),D(2000))
        self.assertEqual(book.settle(date(2024,2,19))['cash'],0)
        self.assertEqual(book.settle(date(2024,2,20))['cash'],D(2000))
        self.assertEqual(book.receivable(date(2024,2,20)),0)
        self.assertEqual(book.settle(date(2024,2,20))['cash'],0)

    def test_replay_and_conflicting_terms(self):
        e=self.event();book=EntitlementBook();asof=datetime(2024,2,1,tzinfo=timezone.utc)
        book.accrue(e,1000,e.ex_date,asof);book.accrue(e,1000,e.ex_date,asof)
        with self.assertRaisesRegex(DataBlocked,'CONFLICTING'):book.accrue(replace(e,cash_per_share=D(3)),1000,e.ex_date,asof)

    def test_future_available_and_naive_asof_cannot_be_used(self):
        e=self.event(available_at='2024-03-01T00:00:00+08:00')
        with self.assertRaisesRegex(DataBlocked,'POINT_IN_TIME'):e.validate(datetime(2024,2,1,tzinfo=timezone.utc))
        with self.assertRaisesRegex(DataBlocked,'TIMEZONE'):self.event().validate(datetime(2024,2,1))

    def test_taiwan_announcement_date_not_utc_date(self):
        e=self.event(announced_at='2024-01-31T23:00:00+00:00',available_at='2024-01-31T23:01:00+00:00')
        with self.assertRaisesRegex(DataBlocked,'LATE'):e.validate(datetime(2024,2,2,tzinfo=timezone.utc))

    def test_split_and_stock_delivery_preserve_shares_without_early_cash(self):
        asof=datetime(2024,2,1,tzinfo=timezone.utc)
        for kind,mult,pay in [('SPLIT',D(2),date(2024,2,1)),('STOCK_DIVIDEND',D('1.1'),date(2024,2,20))]:
            e=self.event(kind=kind,share_multiplier=mult,cash_per_share=D(0),settlement_date=pay)
            book=EntitlementBook();book.accrue(e,1000,e.ex_date,asof)
            result=book.settle(pay)
            self.assertEqual(result['cash'],0);self.assertEqual(result['share_delta']['1100'],int(1000*(mult-1)))

    def test_rights_and_fractional_terms_block(self):
        asof=datetime(2024,2,1,tzinfo=timezone.utc)
        with self.assertRaisesRegex(DataBlocked,'RIGHTS'):EntitlementBook().accrue(self.event(kind='RIGHTS'),1000,date(2024,2,1),asof)
        e=self.event(kind='STOCK_DIVIDEND',share_multiplier=D('1.001'))
        with self.assertRaisesRegex(DataBlocked,'FRACTIONAL'):EntitlementBook().accrue(e,1,e.ex_date,asof)

    def test_verified_delist_terms_settle_once_and_retire_claimed_shares(self):
        e=self.event(kind='DELIST_SETTLEMENT',cash_per_share=D(12))
        b=EntitlementBook();b.accrue(e,1000,e.ex_date,datetime(2024,2,1,tzinfo=timezone.utc))
        self.assertEqual(b.settle(date(2024,2,10))['retired_shares'],{})
        x=b.settle(date(2024,2,20));self.assertEqual(x['cash'],D(12000));self.assertEqual(x['retired_shares'],{'1100':1000})

    def test_coverage_uses_before_ex_open_holdings_and_keeps_global_block(self):
        inventory=self.source().reference_inventory()
        def scenario(day):return dict(strategy_id='UNIT_TEST',start='2024-01-01',end='2024-02-28',fills=[dict(execution_date=day,symbol='1100',quantity=1000)])
        a=holding_coverage([scenario('2024-01-31')],inventory,date(2024,1,1),date(2024,3,1))
        b=holding_coverage([scenario('2024-02-01')],inventory,date(2024,1,1),date(2024,3,1))
        self.assertEqual(len(a['affected_intersections']),1);self.assertEqual(len(b['affected_intersections']),0)
        self.assertEqual(a['status'],b['status']);self.assertEqual(b['status'],'BLOCKED')

    def test_local_archive_continuity_and_no_silent_replacement(self):
        with TemporaryDirectory() as tmp:
            source=Path(tmp)/'a.zip';source.write_bytes(b'UNIT_TEST_ONLY')
            digest=sha256(source.read_bytes()).hexdigest();root=Path(tmp)/'v101_archive'
            with patch('automation.v101.archive.ARTIFACT_SHA256',digest):
                target=preserve(source,root);self.assertEqual(target,preserve(source,root))
                target.write_bytes(b'tampered')
                with self.assertRaisesRegex(DataBlocked,'CHANGED'):preserve(source,root)
                source.write_bytes(b'newer-artifact')
                with self.assertRaisesRegex(DataBlocked,'CONTINUITY'):preserve(source,root)

    def result(self,exposure):
        return dict(curve=[dict(date=f'2024-01-{i+2:02}',equity=1000000.,cash=1000000*(1-e),fees=0.) for i,e in enumerate(exposure)],
            net_return=0.,max_drawdown=0.,fees=0.)

    def test_matching_cannot_pass_cash_only_or_unmatched_books(self):
        self.assertEqual(compare_exposure(self.result([0.]*12),self.result([0.]*12))['status'],'CASH_ONLY_OR_TOO_FEW_ACTIVE_SESSIONS')
        self.assertEqual(compare_exposure(self.result([.2]*12),self.result([.4]*12))['status'],'EXPOSURE_NOT_MATCHED')
        self.assertEqual(compare_exposure(self.result([.2]*12),self.result([.2]*12))['status'],'MATCHED_DIAGNOSTIC_ONLY')

    def test_index_attribution_lags_exposure_and_never_creates_fills(self):
        from types import SimpleNamespace
        r=self.result([0.,1.,1.]);m=SimpleNamespace(benchmark={date(2024,1,2):100.,date(2024,1,3):200.,date(2024,1,4):200.})
        out=attribution(r,m)
        self.assertEqual(out['matched_index_gross_return'],0.)
        self.assertEqual(out['cash_opportunity_gap'],1.)
        self.assertNotIn('fills',out);self.assertIn('NON_TRADABLE',out['mode'])

    def test_paired_gross_target_matches_without_retuning_or_v1_mutation(self):
        m=Market(fixture());d=m.sessions[100];s=SPECS[0]
        a=targets(m,d,s);b=matched_targets(m,d,s,'H2_TREND_MOMENTUM')
        self.assertAlmostEqual(sum(a.values()),sum(b.values()))
        before=registry();r=simulate_matched(m,s,m.sessions[100:135])
        self.assertEqual(registry(),before);self.assertIn('EXPOSURE_CONTROL',r['strategy_id'])
        for f in r['fills']:self.assertLess(f['signal_date'],f['execution_date'])

if __name__=='__main__':unittest.main()
