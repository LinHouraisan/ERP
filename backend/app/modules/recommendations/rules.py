from datetime import date
from decimal import Decimal
from uuid import uuid4
from app.modules.catalog.service import effective

RULE_VERSION = 'phase1-1'


def recommend(facts, demand, policies, day):
    tasks = ['网络故障排查'] if demand.intent == 'FAULT' or any('故障' in i or '网络' in i for i in demand.issues) else []
    result = {'outcome': 'NO_MATCH', 'candidates': [], 'missing_fields': list(demand.missing_fields), 'service_tasks': tasks}
    if demand.intent == 'FAULT':
        return {**result, 'outcome': 'SERVICE_TASK'}
    required = ('monthly_fee', 'verified', 'restrictions', 'discounts')
    missing = [k for k in required if facts.get(k) is None]
    if 'contract_end' not in facts: missing.append('contract_end')
    if missing or demand.missing_fields:
        return {**result, 'outcome': 'NEEDS_INFO', 'missing_fields': missing + demand.missing_fields}
    if facts['contract_end'] and date.fromisoformat(str(facts['contract_end'])) >= day:
        return {**result, 'outcome': 'NEEDS_INFO', 'missing_fields': ['合约尚未结束，需核查变更限制']}
    if facts['restrictions']:
        return {**result, 'missing_fields': ['账号存在办理限制：' + '、'.join(facts['restrictions'])]}
    if demand.intent == 'KEEP_CURRENT':
        return {**result, 'outcome': 'KEEP_CURRENT'}
    current = Decimal(facts['monthly_fee'])
    for p in policies:
        if not effective(p, day) or str(p.product_id) == facts.get('product_id'):
            continue
        if demand.budget is not None and p.monthly_fee is not None and p.monthly_fee > demand.budget:
            continue
        if 'broadband' in demand.must_keep and p.broadband is False:
            continue
        c = p.conditions
        if c.get('verified_required', True) and facts.get('verified') is False: continue
        if c.get('new_customer_only') and facts.get('is_new_customer') is False: continue
        if c.get('minimum_tenure_months', 0) and facts.get('tenure_months') is not None and facts['tenure_months'] < c['minimum_tenure_months']: continue
        if c.get('excludes_discount') in facts['discounts']: continue
        unresolved = []
        if p.monthly_fee is None: unresolved.append('候选月费未知')
        if p.one_time_fee is None: unresolved.append('一次费未知，不能确认总费用')
        if 'broadband' in demand.must_keep and p.broadband is None: unresolved.append('宽带保留情况未知')
        if c.get('new_customer_only') and facts.get('is_new_customer') is None: unresolved.append('新客资格未知')
        if c.get('minimum_tenure_months', 0) and facts.get('tenure_months') is None: unresolved.append('在网时长未知')
        result['candidates'].append({'candidate_id': str(uuid4()), 'product_id': str(p.product_id), 'policy_version_id': str(p.id),
            'monthly_fee': str(p.monthly_fee) if p.monthly_fee is not None else None,
            'one_time_fee': str(p.one_time_fee) if p.one_time_fee is not None else None,
            'monthly_difference': str((current-p.monthly_fee).quantize(Decimal('.01'))) if p.monthly_fee is not None else None,
            'contract_months': p.contract_months, 'promotion_months': p.promotion_months, 'broadband': p.broadband,
            'eligibility': 'unknown' if unresolved else 'eligible', 'evidence_ids': [str(p.id)], 'unresolved_needs': unresolved})
    result['candidates'].sort(key=lambda c: (c['eligibility'] != 'eligible', Decimal(c['monthly_fee']) if c['monthly_fee'] else Decimal('Infinity')))
    result['candidates'] = result['candidates'][:3]
    usable = [c for c in result['candidates'] if c['eligibility'] == 'eligible']
    if usable:
        if demand.intent == 'REDUCE_COST' and all(Decimal(c['monthly_fee']) >= current for c in usable) and (demand.budget is None or current <= demand.budget) and ('broadband' not in demand.must_keep or facts.get('broadband') is True):
            return {**result, 'outcome': 'KEEP_CURRENT', 'candidates': []}
        result['outcome'] = 'OPTIONS'
    elif result['candidates']:
        result['outcome'] = 'NEEDS_INFO'
    return result
