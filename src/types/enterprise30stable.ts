export type StableRun30 = {
  id: string;
  release_version: string;
  run_date: string;
  run_status: string;
  current_stage?: string | null;
  started_at: string;
  completed_at?: string | null;
  stage_results: Array<{
    stage: string;
    status: string;
    critical: boolean;
    error?: string;
  }>;
  blockers: string[];
  error_message?: string | null;
};

export type DataQuality30 = {
  id: number;
  check_date: string;
  check_key: string;
  check_status: string;
  observed_value?: string | null;
  expected_value?: string | null;
  severity: string;
  message: string;
};
