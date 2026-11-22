"""用于确认数据库备份中包含当前应用所需的表。"""
REQUIRED_TABLES = frozenset({
    'phones', 'feedback', 'feedback_request', 'feedback_state',
    'image_review', 'image_review_log', 'back_reference', 'back_reference_log',
    'legacy_drafts', 'legacy_draft_log', 'legacy_publications', 'edit_log', 'research_log',
})


def missing_tables(output):
    present = {line.strip() for line in output.splitlines() if line.strip()}
    return sorted(REQUIRED_TABLES - present)


def parse_table_counts(output):
    counts = {}
    for line in output.splitlines():
        parts = line.split('\t')
        if len(parts) != 2 or parts[0] not in REQUIRED_TABLES or not parts[1].isdigit() or parts[0] in counts:
            raise ValueError('备份表数量结果无效')
        counts[parts[0]] = int(parts[1])
    if set(counts) != REQUIRED_TABLES:
        raise ValueError('备份表数量结果不完整')
    return counts


def parse_table_checksums(output):
    checksums = {}
    for line in output.splitlines():
        parts = line.split('\t')
        if len(parts) != 2 or not parts[0].startswith('phoneguide.'):
            raise ValueError('表校验结果无效')
        table = parts[0][len('phoneguide.'):]
        if table not in REQUIRED_TABLES or not parts[1].isdigit() or table in checksums:
            raise ValueError('表校验结果无效或不受支持')
        checksums[table] = int(parts[1])
    if set(checksums) != REQUIRED_TABLES:
        raise ValueError('表校验结果不完整')
    return checksums
