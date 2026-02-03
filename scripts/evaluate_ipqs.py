#!/usr/bin/env python3
"""IPQS Email Validation Evaluation Script.

This script tests IPQualityScore API to evaluate:
1. Latency (response time for different email types)
2. Accuracy (compared to our free Tier 1 checks)
3. Value (does IPQS catch things our free checks miss?)

Usage:
    # Set API key
    export IPQUALITYSCORE_API_KEY=your_key_here

    # Run evaluation
    uv run python scripts/evaluate_ipqs.py

    # Or with specific emails
    uv run python scripts/evaluate_ipqs.py test@gmail.com user@suspicious.com
"""

import asyncio
import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ava_v1.shared_libraries.email_validator import (
    check_email_validity,
    validate_email_with_ipqs,
    interpret_ipqs_result,
    is_trusted_provider,
    is_disposable_domain,
    has_valid_mx_records,
)

# Test emails - LIMITED TO 10 PER EXECUTION to conserve API credits
#
# Focus on emails that PASS Tier 1 free checks (where IPQS would be called in production)
#
# Run with: python scripts/evaluate_ipqs.py
# Or specific emails: python scripts/evaluate_ipqs.py email1@test.com email2@test.com

TEST_EMAILS = [
    # Legitimate companies - should pass IPQS
    ("contact@anthropic.com", "legitimate", "Real company"),
    ("info@stripe.com", "legitimate", "Real company"),
    ("support@cloudflare.com", "legitimate", "Real company"),

    # Fake usernames at real domains - IPQS should detect these don't exist
    ("xkcd9999test@anthropic.com", "fake_user", "Fake username at real domain"),
    ("notarealuser12345@cloudflare.com", "fake_user", "Fake username at real domain"),

    # Foreign providers - check domain_trust ratings
    ("user@mail.ru", "foreign_provider", "Russian provider"),
    ("test@yandex.com", "foreign_provider", "Russian provider"),

    # Typo domain - IPQS may suggest correction
    ("user@gmial.com", "typo", "Gmail typo - check suggested_domain"),

    # Disposable - IPQS backup check
    ("temp@guerrillamail.com", "disposable", "Disposable domain"),

    # Trusted provider baseline
    ("test@gmail.com", "trusted", "Gmail - baseline comparison"),
]


async def evaluate_single_email(email: str, category: str, description: str) -> dict:
    """Evaluate a single email with both Tier 1 and IPQS."""
    result = {
        "email": email,
        "category": category,
        "description": description,
    }

    # Run Tier 1 checks
    tier1_valid, tier1_reason = await check_email_validity(email)
    result["tier1_valid"] = tier1_valid
    result["tier1_reason"] = tier1_reason

    # Extract domain info
    domain = email.split("@")[1].lower() if "@" in email else ""
    result["is_trusted"] = is_trusted_provider(domain)
    result["is_disposable"] = is_disposable_domain(domain)
    result["has_mx"] = has_valid_mx_records(domain) if domain else False

    # Run IPQS check
    ipqs_data = await validate_email_with_ipqs(email)
    if ipqs_data:
        result["ipqs_latency_ms"] = ipqs_data.get("_latency_ms", 0)
        result["ipqs_error"] = ipqs_data.get("_error")

        if not ipqs_data.get("_error"):
            result["ipqs_fraud_score"] = ipqs_data.get("fraud_score")
            result["ipqs_valid"] = ipqs_data.get("valid")
            result["ipqs_disposable"] = ipqs_data.get("disposable")
            result["ipqs_smtp_score"] = ipqs_data.get("smtp_score")
            result["ipqs_overall_score"] = ipqs_data.get("overall_score")
            result["ipqs_deliverability"] = ipqs_data.get("deliverability")
            result["ipqs_recent_abuse"] = ipqs_data.get("recent_abuse")
            result["ipqs_catch_all"] = ipqs_data.get("catch_all")
            result["ipqs_honeypot"] = ipqs_data.get("honeypot")
            result["ipqs_domain_trust"] = ipqs_data.get("domain_trust")
            result["ipqs_suggested_domain"] = ipqs_data.get("suggested_domain")

            # Interpret IPQS result (now returns 3 values)
            ipqs_valid, ipqs_reason, ipqs_details = interpret_ipqs_result(ipqs_data)
            result["ipqs_interpretation_valid"] = ipqs_valid
            result["ipqs_interpretation_reason"] = ipqs_reason
            result["ipqs_interpretation_details"] = ipqs_details
    else:
        result["ipqs_error"] = "API key not configured"

    return result


async def run_evaluation(emails: list[tuple[str, str, str]]):
    """Run evaluation on all test emails."""
    print("=" * 80)
    print("IPQS Email Validation Evaluation")
    print("=" * 80)

    print(f"\n📧 Testing {len(emails)} emails (each = 1 IPQS API request)")

    api_key = os.getenv("IPQUALITYSCORE_API_KEY")
    if not api_key:
        print("\n⚠️  WARNING: IPQUALITYSCORE_API_KEY not set. IPQS checks will be skipped.")
        print("Set it with: export IPQUALITYSCORE_API_KEY=your_key_here\n")

    total_start_time = time.perf_counter()

    results = []
    total_ipqs_latency = 0
    ipqs_count = 0
    latencies = []  # Track individual latencies for stats

    for email, category, description in emails:
        print(f"\nTesting: {email}")
        print(f"  Category: {category} | {description}")

        result = await evaluate_single_email(email, category, description)
        results.append(result)

        # Print Tier 1 result
        t1_status = "PASS" if result["tier1_valid"] else "REJECT"
        t1_reason = result["tier1_reason"] or ""
        print(f"  Tier 1:  {t1_status} {t1_reason}")

        # Print IPQS result
        if "ipqs_error" in result and result["ipqs_error"]:
            latency = result.get("ipqs_latency_ms", 0)
            if latency:
                total_ipqs_latency += latency
                ipqs_count += 1
            print(f"  IPQS:    ERROR - {result['ipqs_error']}")
        elif "ipqs_fraud_score" in result:
            latency = result.get("ipqs_latency_ms", 0)
            total_ipqs_latency += latency
            ipqs_count += 1
            latencies.append(latency)

            ipqs_status = "PASS" if result.get("ipqs_interpretation_valid") else "REJECT"
            ipqs_reason = result.get("ipqs_interpretation_reason") or ""

            # PROMINENT LATENCY DISPLAY
            print(f"  ⏱️  LATENCY: {latency:.0f}ms")
            print(f"  IPQS:    {ipqs_status} {ipqs_reason}")
            print(f"           fraud={result['ipqs_fraud_score']}, "
                  f"smtp={result['ipqs_smtp_score']}, "
                  f"overall={result.get('ipqs_overall_score')}, "
                  f"valid={result['ipqs_valid']}")
            print(f"           disposable={result['ipqs_disposable']}, "
                  f"catch_all={result.get('ipqs_catch_all')}, "
                  f"honeypot={result.get('ipqs_honeypot')}")
            print(f"           domain_trust={result.get('ipqs_domain_trust')}")

            # Show typo suggestion if available
            if result.get("ipqs_suggested_domain"):
                print(f"           >>> TYPO SUGGESTION: Did you mean @{result['ipqs_suggested_domain']}?")

            # Show warnings from interpretation
            details = result.get("ipqs_interpretation_details", {})
            if details.get("warnings"):
                print(f"           >>> INFO: {', '.join(details['warnings'])}")

        # Highlight disagreements
        if result["tier1_valid"] != result.get("ipqs_interpretation_valid", result["tier1_valid"]):
            print(f"  >>> DISAGREEMENT: Tier1={result['tier1_valid']}, IPQS={result.get('ipqs_interpretation_valid')}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    # LATENCY STATS - Prominent display
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        sorted_latencies = sorted(latencies)
        median_latency = sorted_latencies[len(sorted_latencies) // 2]

        print(f"\n⏱️  LATENCY ANALYSIS ({len(latencies)} requests)")
        print(f"  ├─ Min:     {min_latency:,.0f}ms")
        print(f"  ├─ Max:     {max_latency:,.0f}ms")
        print(f"  ├─ Avg:     {avg_latency:,.0f}ms")
        print(f"  ├─ Median:  {median_latency:,.0f}ms")
        print(f"  └─ Total:   {sum(latencies):,.0f}ms ({sum(latencies)/1000:.1f}s)")

        print(f"\n  Individual request times:")
        for i, (lat, res) in enumerate(zip(latencies, [r for r in results if r.get("ipqs_latency_ms")]), 1):
            domain = res["email"].split("@")[1] if "@" in res["email"] else "?"
            print(f"    {i:2d}. {lat:>6,.0f}ms  @{domain}")

    # Count disagreements
    disagreements = [r for r in results
                     if r["tier1_valid"] != r.get("ipqs_interpretation_valid", r["tier1_valid"])]

    print(f"\nAgreement:")
    print(f"  Tier 1 and IPQS agreed: {len(results) - len(disagreements)}/{len(results)}")

    if disagreements:
        print(f"\nDisagreements ({len(disagreements)}):")
        for r in disagreements:
            print(f"  - {r['email']}: Tier1={r['tier1_valid']}, IPQS={r.get('ipqs_interpretation_valid')}")

    # Value analysis
    print("\n📊 VALIDATION RESULTS:")

    # Cases where IPQS caught something Tier 1 missed (the key metric!)
    ipqs_caught = [r for r in results
                   if r["tier1_valid"] and not r.get("ipqs_interpretation_valid", True)]

    if ipqs_caught:
        print(f"\n  🚨 IPQS CAUGHT (Tier 1 missed): {len(ipqs_caught)}")
        for r in ipqs_caught:
            print(f"    - {r['email']}")
            print(f"      Reason: {r.get('ipqs_interpretation_reason')}")
            print(f"      fraud={r.get('ipqs_fraud_score')}, smtp={r.get('ipqs_smtp_score')}")
    else:
        print(f"\n  IPQS caught (Tier 1 missed): 0")

    # Emails that passed both
    both_passed = [r for r in results
                   if r["tier1_valid"] and r.get("ipqs_interpretation_valid", False)]
    print(f"\n  ✅ Both passed: {len(both_passed)}")

    # Tier 1 rejections
    tier1_rejects = [r for r in results if not r["tier1_valid"]]
    print(f"  🚫 Tier 1 rejected: {len(tier1_rejects)}")

    # Catch-all warnings
    catch_all_warnings = [r for r in results if r.get("ipqs_catch_all")]
    if catch_all_warnings:
        print(f"\n  ⚠️  Catch-All Domains: {len(catch_all_warnings)}")
        for r in catch_all_warnings:
            print(f"    - {r['email']}")

    # Total execution time
    total_time = time.perf_counter() - total_start_time
    print(f"\n⏱️  Total execution time: {total_time:.1f}s")

    print("\n" + "=" * 80)


async def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        # Custom emails from command line
        emails = [(email, "custom", "User provided") for email in sys.argv[1:]]
    else:
        emails = TEST_EMAILS

    await run_evaluation(emails)


if __name__ == "__main__":
    asyncio.run(main())
