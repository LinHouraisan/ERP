def issue_metrics(pairs):
    tp = fp = fn = 0
    for expected, actual in pairs:
        expected, actual = set(expected), set(actual)
        tp += len(expected & actual)
        fp += len(actual - expected)
        fn += len(expected - actual)
    return {'tp': tp, 'fp': fp, 'fn': fn, 'precision': tp/(tp+fp) if tp+fp else None,
        'recall': tp/(tp+fn) if tp+fn else None, 'false_positive_count': fp}
