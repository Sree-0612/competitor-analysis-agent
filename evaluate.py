"""
CompeteIQ - Evaluation Suite
Automated test cases to validate agent accuracy and robustness.
Demonstrates production-quality testing approach.

Run: python evaluate.py
"""

import json
import time
from typing import Any

from tabulate import tabulate

from tools.security import validate_url, RateLimiter
from tools.scraper import scrape_website


# ============================================================
# TEST CASES
# ============================================================

# --- Security Tests ---
SECURITY_TEST_CASES = [
    # (input_url, should_pass, test_description)
    ("https://www.bmw.com", True, "Valid HTTPS URL"),
    ("https://www.apple.com/iphone", True, "Valid URL with path"),
    ("http://www.nike.com", True, "Valid HTTP URL"),
    ("", False, "Empty URL"),
    ("not-a-url", False, "Invalid format"),
    ("javascript:alert(1)", False, "XSS attempt"),
    ("https://localhost/admin", False, "SSRF - localhost"),
    ("https://127.0.0.1/api", False, "SSRF - loopback IP"),
    ("https://192.168.1.1/router", False, "SSRF - private IP"),
    ("https://10.0.0.1/internal", False, "SSRF - internal network"),
    ("<script>alert('xss')</script>", False, "Script injection"),
    ("https://example.com/" + "A" * 3000, False, "URL length overflow"),
    ("ftp://files.company.com", False, "Non-HTTP scheme"),
    ("data:text/html,<script>", False, "Data URL injection"),
]

# --- Scraper Tests ---
SCRAPER_TEST_CASES = [
    # (url, expected_field, test_description)
    ("https://www.google.com", "title", "Google homepage scraping"),
    ("https://httpbin.org/html", "main_content", "HTML content extraction"),
    ("https://nonexistent-domain-xyz123.com", "error", "Graceful failure on bad domain"),
]

# --- Rate Limiter Tests ---
RATE_LIMIT_TEST_CASES = [
    # (num_requests, max_allowed, should_final_pass, description)
    (3, 5, True, "Under limit - should pass"),
    (5, 5, False, "At limit - should block"),
    (6, 5, False, "Over limit - should block"),
]


# ============================================================
# TEST RUNNER
# ============================================================

def run_security_tests() -> list[dict]:
    """Run all URL validation security tests."""
    results = []
    for url, should_pass, description in SECURITY_TEST_CASES:
        is_valid, message = validate_url(url)
        passed = is_valid == should_pass
        results.append({
            "test": description,
            "input": url[:50] + "..." if len(url) > 50 else url,
            "expected": "PASS" if should_pass else "BLOCK",
            "actual": "PASS" if is_valid else "BLOCK",
            "status": "✅" if passed else "❌",
        })
    return results


def run_rate_limit_tests() -> list[dict]:
    """Run rate limiter tests."""
    results = []
    for num_requests, max_allowed, should_final_pass, description in RATE_LIMIT_TEST_CASES:
        limiter = RateLimiter(max_requests=max_allowed, window_seconds=60)

        # Make requests
        final_result = True
        for _ in range(num_requests):
            allowed, _ = limiter.is_allowed()
            final_result = allowed

        passed = final_result == should_final_pass
        results.append({
            "test": description,
            "input": f"{num_requests} requests (max {max_allowed})",
            "expected": "ALLOW" if should_final_pass else "BLOCK",
            "actual": "ALLOW" if final_result else "BLOCK",
            "status": "✅" if passed else "❌",
        })
    return results


def run_scraper_tests() -> list[dict]:
    """Run web scraper tests."""
    results = []
    for url, expected_field, description in SCRAPER_TEST_CASES:
        try:
            result = scrape_website(url)
            if expected_field == "error":
                # We expect failure
                passed = not result.get("success", True)
            else:
                # We expect success with the field present
                passed = result.get("success", False) and expected_field in result
        except Exception as e:
            passed = expected_field == "error"

        results.append({
            "test": description,
            "input": url,
            "expected": f"Has '{expected_field}'",
            "actual": "Success" if passed else "Failed",
            "status": "✅" if passed else "❌",
        })
    return results


# ============================================================
# MAIN EVALUATION
# ============================================================

def main():
    """Run complete evaluation suite."""
    print("\n" + "=" * 70)
    print("  CompeteIQ - Evaluation Suite")
    print("  Testing agent accuracy, security, and robustness")
    print("=" * 70 + "\n")

    all_results = []
    total_tests = 0
    total_passed = 0

    # --- Security Tests ---
    print("🛡️  SECURITY TESTS (URL Validation & SSRF Prevention)")
    print("-" * 60)
    security_results = run_security_tests()
    all_results.extend(security_results)

    headers = ["Test", "Input", "Expected", "Actual", "Status"]
    table_data = [[r["test"], r["input"][:30], r["expected"], r["actual"], r["status"]]
                  for r in security_results]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

    sec_passed = sum(1 for r in security_results if r["status"] == "✅")
    sec_total = len(security_results)
    total_tests += sec_total
    total_passed += sec_passed
    print(f"\n  Result: {sec_passed}/{sec_total} passed\n")

    # --- Rate Limit Tests ---
    print("⏱️  RATE LIMITING TESTS")
    print("-" * 60)
    rate_results = run_rate_limit_tests()
    all_results.extend(rate_results)

    table_data = [[r["test"], r["input"], r["expected"], r["actual"], r["status"]]
                  for r in rate_results]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

    rate_passed = sum(1 for r in rate_results if r["status"] == "✅")
    rate_total = len(rate_results)
    total_tests += rate_total
    total_passed += rate_passed
    print(f"\n  Result: {rate_passed}/{rate_total} passed\n")

    # --- Scraper Tests ---
    print("🌐  WEB SCRAPER TESTS")
    print("-" * 60)
    scraper_results = run_scraper_tests()
    all_results.extend(scraper_results)

    table_data = [[r["test"], r["input"][:30], r["expected"], r["actual"], r["status"]]
                  for r in scraper_results]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

    scrape_passed = sum(1 for r in scraper_results if r["status"] == "✅")
    scrape_total = len(scraper_results)
    total_tests += scrape_total
    total_passed += scrape_passed
    print(f"\n  Result: {scrape_passed}/{scrape_total} passed\n")

    # --- Final Summary ---
    print("=" * 70)
    print(f"  TOTAL: {total_passed}/{total_tests} tests passed "
          f"({(total_passed / total_tests * 100):.0f}% accuracy)")
    print("=" * 70)

    if total_passed == total_tests:
        print("  🎉 ALL TESTS PASSED - System is production-ready!")
    else:
        failed = total_tests - total_passed
        print(f"  ⚠️  {failed} test(s) failed - review before deployment")

    return total_passed == total_tests


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
