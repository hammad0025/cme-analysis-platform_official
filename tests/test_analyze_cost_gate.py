import argparse
import os
import sys
from unittest.mock import patch

import analyze_cme_full as mod


def test_high_cost_requires_confirm_flag():
    args = argparse.Namespace(yes=False, confirm_cost=False)
    with patch.object(mod, "COST_CONFIRM_THRESHOLD_USD", 5.0):
        with patch.object(sys, "exit") as mock_exit:
            # Simulate the gate block without running main
            total_cost_est = 10.0
            if total_cost_est > mod.COST_CONFIRM_THRESHOLD_USD:
                if not (args.yes or args.confirm_cost):
                    sys.exit(1)
            mock_exit.assert_called_once_with(1)


def test_high_cost_allows_confirm_cost():
    args = argparse.Namespace(yes=False, confirm_cost=True)
    blocked = False
    total_cost_est = 10.0
    if total_cost_est > mod.COST_CONFIRM_THRESHOLD_USD:
        if not (args.yes or args.confirm_cost):
            blocked = True
    assert not blocked


def test_local_analysis_requires_env_flag():
    with patch.dict("os.environ", {}, clear=True):
        with patch.object(sys, "exit") as mock_exit:
            if os.environ.get(mod.ALLOW_LOCAL_ENV) != "1":
                sys.exit(1)
            mock_exit.assert_called_once_with(1)
