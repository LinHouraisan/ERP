def test_metrics_handle_zero_denominator():
    from app.modules.evaluations.metrics import issue_metrics
    empty=issue_metrics([])
    assert empty['precision'] is None and empty['recall'] is None
    result=issue_metrics([({'PRICE','CONTRACT'},{'PRICE','EXTRA'}),({'EXPIRED'},{'EXPIRED'})])
    assert result == {'tp':2,'fp':1,'fn':1,'precision':2/3,'recall':2/3,'false_positive_count':1}


def test_cases_are_frozen_split_and_live_requires_review():
    from pathlib import Path
    import pytest
    from app.modules.evaluations.cli import load_cases, validate_live
    cases=load_cases(Path('evaluation/cases.jsonl'))
    assert len(cases)==30 and sum(c.split=='dev' for c in cases)==20
    assert len({c.id for c in cases})==30
    with pytest.raises(ValueError,match='核对'):
        validate_live(cases,30)


def test_live_smoke_has_budget_and_does_not_use_holdout():
    from pathlib import Path
    import pytest
    from app.modules.evaluations.cli import load_cases, validate_live
    cases=load_cases(Path('evaluation/cases.jsonl'))
    dev=[c for c in cases if c.split=='dev']
    validate_live(dev,40,smoke=True)
    with pytest.raises(ValueError,match='预算'): validate_live(dev,1,smoke=True)
    with pytest.raises(ValueError,match='开发集'): validate_live(cases,60,smoke=True)


async def test_smoke_persists_outputs_without_quality_scores(client,monkeypatch):
    from pathlib import Path
    from app.modules.evaluations.cli import load_cases,run_batch
    from app.integrations import ai
    monkeypatch.setenv('DEEPSEEK_API_KEY','fixed-smoke-test')
    monkeypatch.setenv('AI_MODE','offline')
    async def fixed(*args,**kwargs): return {'complete':True,'findings':[]},None,'fixed-smoke-test'
    monkeypatch.setattr(ai,'generate',fixed)
    result=await run_batch(load_cases(Path('evaluation/cases.jsonl'))[:1],1,live=True,max_calls=2,smoke=True)
    assert result['settings']['purpose']=='connection_smoke'
    assert result['settings']['labels_confirmed'] is False
    assert result['metrics']=={'evaluated_cases':1,'failed_cases':0,'total_cases':1}
