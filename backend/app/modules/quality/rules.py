import re
from decimal import Decimal
from app.modules.catalog.service import effective


def finding(rule, excerpt, policies, explanation, revision):
    return {'rule_id': rule, 'field_or_excerpt': excerpt, 'evidence_ids': [str(p.id) for p in policies],
            'explanation': explanation, 'suggested_revision': revision}


def check_text(text, policies, day):
    findings = []
    for p in policies:
        if not effective(p, day):
            findings.append(finding('EXPIRED_POLICY', '有效期', [p], '政策不在有效期内', '选择有效政策并重新检查'))
    # ponytail: only explicit labelled amounts are parsed; ambiguous prose always needs human review.
    monthly = re.findall(r'月费\s*[：:]?\s*(\d+(?:\.\d{1,2})?)\s*元', text)
    if len(policies) == 1:
        p = policies[0]
        if monthly and p.monthly_fee is not None and any(Decimal(v) != p.monthly_fee for v in monthly):
            findings.append(finding('PRICE_MISMATCH', '、'.join(monthly), [p], '文案月费与政策不符', f'按政策核查月费 {p.monthly_fee} 元'))
        if p.contract_months and not re.search(rf'合约\s*{p.contract_months}\s*个?月', text):
            findings.append(finding('CONTRACT_OMISSION', text, [p], '未明确披露新合约期限', f'明确说明合约 {p.contract_months} 个月'))
    hard = bool(findings)
    if not monthly or len(policies) != 1:
        findings.append(finding('INCOMPLETE_EXTRACTION', text, policies, '无法完整确定文本中的费用及依据', '补齐具体费用、合约与政策版本后复核'))
    return ('BLOCKED' if hard else 'NEEDS_REVIEW'), findings


def check_candidate(candidate, policies, day):
    findings = []
    p = next((p for p in policies if str(p.id) == candidate['policy_version_id']), None)
    if p is None:
        return 'BLOCKED', [finding('UNKNOWN_EVIDENCE', 'policy_version_id', [], '方案依据不存在', '重新生成方案')]
    if not effective(p, day): findings.append(finding('EXPIRED_POLICY', '有效期', [p], '政策已过期或尚未生效', '重新生成方案'))
    for name in ('monthly_fee', 'one_time_fee'):
        actual, expected = candidate[name], getattr(p, name)
        if actual is None or expected is None:
            findings.append(finding('UNKNOWN_FACT', name, [p], '费用资料不完整', '核查费用后重新生成方案'))
        elif Decimal(actual) != expected:
            findings.append(finding('PRICE_MISMATCH', name, [p], '候选费用与政策不同', '按有效政策重新生成'))
    if candidate['contract_months'] != p.contract_months:
        findings.append(finding('CONTRACT_OMISSION', 'contract_months', [p], '合约期限与政策不同', '补齐合约期限'))
    if candidate['eligibility'] != 'eligible':
        findings.append(finding('UNKNOWN_ELIGIBILITY', 'eligibility', [p], '当前资格不可确认', '补齐资料后重新生成'))
    return ('BLOCKED' if findings else 'PASS'), findings
