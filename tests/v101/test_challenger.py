import json
import unittest
from dataclasses import replace
from datetime import date,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from automation.v101.specs import SPECS,CONTROL,registry
from automation.v101.research import Market,DataBlocked,costs,targets,simulate,folds,write_once
from automation.v101.forward import freeze,run_forward,root_guard

# Synthetic deterministic OHLCV is ONLY unit-test input, never a performance artifact.
def fixture(n=220):
    out=[];d=date(2024,1,2)
    for i in range(n):
        while d.weekday()>4:d+=timedelta(days=1)
        rows=[]
        for j in range(15):
            value=20+j+i*(0.03+j*0.001)
            rows.append(dict(symbol=str(1100+j),open=str(value),high=str(value*1.02),
                low=str(value*.98),close=str(value*1.001),volume=10_000_000,observation_id=f'TEST_ONLY:{i}:{j}'))
        out.append(dict(date=d.isoformat(),bars=rows,benchmark=str(10000+i*3),source_sha256=f'TEST_ONLY_{i}'))
        d+=timedelta(days=1)
    return out

class ChallengerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.days=fixture();cls.market=Market(cls.days)

    def test_future_prices_do_not_change_earlier_decision(self):
        t=self.market.sessions[100]
        truncated=Market(self.days[:101])
        self.assertEqual(targets(self.market,t,SPECS[0]),targets(truncated,t,SPECS[0]))

    def test_current_universe_does_not_intersect_future_survivors(self):
        days=json.loads(json.dumps(self.days))
        days[-1]['bars']=[b for b in days[-1]['bars'] if b['symbol']!='1101']
        m=Market(days);t=m.sessions[100]
        self.assertEqual(m.ranked(t),self.market.ranked(t))
        self.assertIn('1101',m.ranked(t))

    def test_no_same_day_or_future_fill(self):
        r=simulate(self.market,SPECS[0],self.market.sessions[100:135])
        self.assertGreater(len(r['fills']),0)
        for f in r['fills']:
            self.assertLess(f['signal_date'],f['execution_date'])
            d=date.fromisoformat(f['execution_date']); s=f['symbol']
            self.assertEqual(f['actual_open'],float(self.market.rows[d][s].open))
            self.assertEqual(f['quantity']%1000,0)

    def test_future_feed_rejected(self):
        days=fixture(2);days[-1]['date']='2099-01-01'
        with self.assertRaisesRegex(DataBlocked,'FUTURE'):Market(days)

    def test_stale_feed_rejected(self):
        with self.assertRaisesRegex(DataBlocked,'STALE'):Market(self.days,expected_end='2026-11-02')

    def test_duplicate_dates_and_symbols_rejected(self):
        with self.assertRaisesRegex(DataBlocked,'DUPLICATE'):Market([self.days[0],self.days[0]])
        days=fixture(2);days[0]['bars'].append(days[0]['bars'][0])
        with self.assertRaisesRegex(DataBlocked,'DUPLICATE'):Market(days)

    def test_fee_tax_slippage_and_minimum(self):
        self.assertAlmostEqual(costs(100000,'BUY',CONTROL),242.5)
        self.assertAlmostEqual(costs(100000,'SELL',CONTROL),542.5)
        self.assertAlmostEqual(costs(100,'BUY',CONTROL),20.1)
        self.assertAlmostEqual(costs(100000,'SELL',CONTROL,2),785)

    def test_cash_and_equity_reconcile(self):
        r=simulate(self.market,CONTROL,self.market.sessions[100:135])
        cash=1_000_000; positions={};fees=0
        for point in r['curve']:
            for f in r['fills']:
                if f['execution_date']==point['date']:
                    cash-=f['quantity']*f['actual_open']+f['cost'];fees+=f['cost']
                    positions[f['symbol']]=positions.get(f['symbol'],0)+f['quantity']
            day=self.market.rows[date.fromisoformat(point['date'])]
            equity=cash+sum(float(day[s].close)*q for s,q in positions.items())
            self.assertAlmostEqual(equity,point['equity'],places=6)
            self.assertGreaterEqual(cash,0)
        self.assertAlmostEqual(fees,r['fees'])

    def test_weight_and_exposure_caps(self):
        w=targets(self.market,self.market.sessions[100],SPECS[0])
        self.assertLessEqual(sum(w.values()),.90000001)
        self.assertLessEqual(max(w.values()),.20)

    def test_implementation_and_parameter_change_account_fingerprint(self):
        s=SPECS[0]
        self.assertNotEqual(s.fingerprint,replace(s,target_annual_vol=.13).fingerprint)
        with patch('automation.v101.specs.implementation_digest',return_value='changed'):
            changed=s.account_id
        self.assertNotEqual(changed,s.account_id)

    def test_duplicate_replay_is_idempotent_conflict_blocks(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'run.json';write_once(p,{'fingerprint':'A'});write_once(p,{'fingerprint':'A'})
            with self.assertRaisesRegex(DataBlocked,'CONFLICT'):write_once(p,{'fingerprint':'B'})

    def test_original_accounts_cannot_be_output(self):
        for p in ('artifacts/v10_forward_store','v10-original-readonly','accounts'):
            with self.assertRaises(DataBlocked):root_guard(p)
        with TemporaryDirectory() as tmp:
            original=Path(tmp)/'v10_forward_store';original.mkdir();f=original/'sealed';f.write_bytes(b'sealed')
            with self.assertRaises(DataBlocked):root_guard(original/'v101_bad')
            self.assertEqual(f.read_bytes(),b'sealed')

    def test_frozen_registry_rejects_fingerprint_changes(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'v101_test';freeze(root,date.today())
            with patch('automation.v101.forward.registry',return_value={'changed':True}):
                with self.assertRaisesRegex(DataBlocked,'CONFLICT'):freeze(root,date.today())

    def test_corporate_action_claim_cannot_activate_forward(self):
        from types import SimpleNamespace
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(DataBlocked,'VERIFIED_CORPORATE_ACTION_ADAPTER'):
                run_forward(Path(tmp)/'v101_test',SimpleNamespace(sessions=[date.today()]),date.today(),True)
            with self.assertRaisesRegex(DataBlocked,'CORPORATE_ACTIONS_NOT_VERIFIED'):
                run_forward(Path(tmp)/'v101_test',SimpleNamespace(sessions=[date.today()]),date.today(),False)

    def test_missing_holdings_never_fabricate_delisting_fill(self):
        r=simulate(self.market,CONTROL,self.market.sessions[100:102]);symbol=r['fills'][0]['symbol']
        days=json.loads(json.dumps(self.days));days[102]['bars']=[b for b in days[102]['bars'] if b['symbol']!=symbol]
        with self.assertRaisesRegex(DataBlocked,'MISSING_HELD'):simulate(Market(days),CONTROL,self.market.sessions[100:104])

    def test_next_open_volume_is_not_used_for_sizing(self):
        days=json.loads(json.dumps(self.days))
        for b in days[101]['bars']:b['volume']=1
        changed=Market(days)
        a=simulate(self.market,CONTROL,self.market.sessions[100:102])
        b=simulate(changed,CONTROL,changed.sessions[100:102])
        self.assertEqual(a['fills'],b['fills'])

    def test_walkforward_embargo_and_final_holdout_disjoint(self):
        plan=folds(self.market.sessions);seen=set()
        self.assertGreater(len(plan),1)
        for f in plan:
            self.assertEqual(len(f['embargo']),5)
            self.assertLess(f['train'][-1],f['embargo'][0]);self.assertLess(f['embargo'][-1],f['test'][0])
            self.assertFalse(seen.intersection(f['test']));seen.update(f['test'])
        self.assertEqual(plan[-1]['name'],'FINAL_HOLDOUT')
        self.assertEqual(len(plan[-1]['test']),30)

    def test_missing_intermediate_session_blocks(self):
        with self.assertRaisesRegex(DataBlocked,'INTERMEDIATE'):
            simulate(self.market,CONTROL,[self.market.sessions[100],self.market.sessions[102]])

    def test_immutable_zip_must_match_extracted_tree(self):
        import hashlib
        from zipfile import ZipFile
        from automation.v101.baseline import audit
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';root.mkdir();(root/'sealed').write_bytes(b'tampered')
            archive=Path(tmp)/'original.zip'
            with ZipFile(archive,'w') as z:z.writestr('sealed',b'authentic')
            digest=hashlib.sha256(archive.read_bytes()).hexdigest()
            with patch('automation.v101.baseline.ARTIFACT_SHA256',digest):
                with self.assertRaisesRegex(ValueError,'EXTRACTED_TREE'):
                    audit(root,archive)

    def test_cash_only_outcome_is_not_profitability_evidence(self):
        from automation.v101.report import summarize
        r=simulate(self.market,replace(CONTROL,lot=1_000_000),self.market.sessions[100:135])
        x=summarize(r)
        self.assertTrue(x['no_trade_cash_only'])
        self.assertEqual(x['average_exposure'],0)
        self.assertFalse(x['promotion_eligible'])
        self.assertIsNone(x['sharpe'])

    def test_original_v9_v10_dashboard_files_untouched(self):
        import subprocess
        root=Path(__file__).resolve().parents[2]
        changed=subprocess.check_output(['git','diff','--name-only','HEAD','--',
            'automation/v10','artifacts/v10_forward_store','src/pages/MultiStrategyV10.tsx',
            'src/pages/DashboardV9.tsx'],cwd=root,text=True)
        self.assertEqual(changed.strip(),'')

    def test_registry_contains_no_original_v10_strategy(self):
        self.assertTrue(all(s['strategy_id'].startswith('V101_') for s in registry()['strategies']))
        self.assertFalse(registry()['promotion_enabled'])

if __name__=='__main__':unittest.main()
