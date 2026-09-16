import json
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest.mock import Mock, patch

from news_research import research_news, usage_cost_bounds, astra_output_allowance, SOL, ASTRA


def response(model=SOL, text="1. A useful launch. Source: https://example.com/launch", *, incoming=4000, outgoing=2500):
    return Obj(model=model, service_tier="default", status="completed", output_text=text,
               output=[Obj(type="web_search_call")] if model == SOL else [],
               usage=Obj(input_tokens=incoming, output_tokens=outgoing,
                         input_tokens_details=Obj(cached_tokens=0, cache_write_tokens=0)))


class ResearchBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = Mock()
        self.client.with_options.return_value = self.client
        self.client.responses.input_tokens.count.return_value = Obj(input_tokens=1800)
        self.client.responses.create.side_effect = [response(), response(ASTRA, outgoing=2000)]
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_research(self, **kwargs):
        return research_news(self.client, "Current AI news with practical developer impact", use_astra=True,
                             output_directory=self.temp.name, **kwargs)

    def report(self):
        return json.loads(next(Path(self.temp.name).glob("*/research-cost.json")).read_text())

    def test_complete_research_reserves_before_astra_and_caps_combined_cost(self):
        self.run_research()
        report = self.report()
        baseline = Decimal(report["sol"]["cost_lower_usd"])
        self.assertLessEqual(Decimal(report["maximum_total_usd"]), 3 * baseline)
        calls = self.client.responses.create.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].kwargs["model"], SOL)
        self.assertEqual(calls[0].kwargs["extra_body"], {"max_tool_calls": 6})
        self.assertEqual(calls[1].kwargs["model"], ASTRA)
        self.assertNotIn("tools", calls[1].kwargs)
        self.assertNotIn("previous_response_id", calls[1].kwargs)
        self.assertEqual(calls[1].kwargs["service_tier"], "default")
        self.assertEqual(report["status"], "astra_complete")

    def test_tiny_historical_budget_skips_astra(self):
        os.environ["RESEARCH_SOL_BASELINE_USD"] = "0.03"
        result = self.run_research()
        self.client.responses.create.assert_called_once()
        self.assertIn("useful launch", result)
        self.assertEqual(self.report()["status"], "sol_used_budget_limit")

    def test_unknown_input_count_never_sends_unbudgeted_astra(self):
        self.client.responses.input_tokens.count.side_effect = TimeoutError()
        self.run_research()
        self.client.responses.create.assert_called_once()

    def test_astra_timeout_keeps_sol_and_never_retries(self):
        self.client.responses.create.side_effect = [response(), TimeoutError()]
        self.assertIn("useful launch", self.run_research())
        self.assertEqual(self.client.responses.create.call_count, 2)
        self.assertIn("charge_uncertain", self.report()["status"])

    def test_search_timeout_never_retries_paid_research(self):
        self.client.responses.create.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            self.run_research()
        self.client.responses.create.assert_called_once()

    def test_invented_link_or_truncation_uses_verified_sol_brief(self):
        edited = response(ASTRA, "Claim: https://invented.example/news")
        self.client.responses.create.side_effect = [response(), edited]
        self.assertNotIn("invented", self.run_research())
        self.assertEqual(self.report()["status"], "sol_used_editorial_validation_failed")

    def test_no_search_evidence_stops_news_generation(self):
        ungrounded = response()
        ungrounded.output = []
        self.client.responses.create.side_effect = [ungrounded]
        with self.assertRaisesRegex(RuntimeError, "without web evidence"):
            self.run_research()

    def test_cache_writes_and_search_are_included(self):
        r = response(incoming=1000, outgoing=100)
        r.usage.input_tokens_details = Obj(cached_tokens=200, cache_write_tokens=300)
        lower, upper, _ = usage_cost_bounds(r, SOL)
        self.assertEqual(lower, Decimal("0.01558"))
        self.assertEqual(lower, upper)

    def test_budget_math_includes_maximum_input_and_reasoning_output(self):
        for budget in ("0.01", "0.10", "0.20", "0.40"):
            for incoming in (0, 1000, 9000, 25000):
                limit = astra_output_allowance(incoming, Decimal(budget))
                if limit:
                    reserved = (Decimal(incoming) * Decimal("12.5") + limit * 50) / 1_000_000
                    self.assertLessEqual(reserved, Decimal(budget))
        self.assertEqual(astra_output_allowance(300_000, Decimal("50")), 0)


if __name__ == "__main__":
    unittest.main()
