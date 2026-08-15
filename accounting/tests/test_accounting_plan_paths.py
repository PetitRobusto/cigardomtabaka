from pathlib import Path

from django.test import TestCase


REQUIRED_EXISTING_PATHS = (
    'CONTEXT.md',
    'docs/superpowers/specs/2026-08-10-internal-accounting-module-design.md',
    'docs/superpowers/specs/2026-08-13-business-workspace-day1-design.md',
    'accounting/models.py', 'accounting/services.py', 'accounting/day1.py',
    'cigars/models.py', 'cigars/services.py', 'cigars/agent_api.py',
    'cigars/sales_accounting.py', 'cigars/sales_api.py',
    'frontend/src/api.ts', 'frontend/src/features/guides/guideInteractions.ts',
    'frontend/src/features/guides/ContextTour.tsx',
)

EXPECTED_REVIEW_PATHS = (
    'docs/reviews/2026-08-14-accounting-actions-review-a.md',
    'docs/reviews/2026-08-14-accounting-actions-review-b.md',
)


class AccountingPlanReferencePathTest(TestCase):
    def test_required_reference_paths_exist(self):
        for path in REQUIRED_EXISTING_PATHS:
            self.assertTrue(Path(path).is_file(), path)

    def test_review_artifacts_exist(self):
        # 审查文档必须在合并前落盘。
        for path in EXPECTED_REVIEW_PATHS:
            self.assertTrue(Path(path).is_file(), path)
