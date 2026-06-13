"""雪茄搜索引擎 — 零 HTTP 依赖，纯算法层"""
from cigars.search.scoring import score_cigar
from cigars.search.constants import DEFAULT_RESULT_LIMIT, MIN_SEARCH_SCORE


def split_search_terms(q):
    """按 CJK/非 CJK 边界拆分查询词"""
    import re
    terms = re.findall(r'[\u4e00-\u9fff]+|[^\u4e00-\u9fff\s]+', q)
    return [t.lower() for t in terms if len(t) >= 1]


class CigarSearchEngine:
    """
    雪茄搜索引擎。
    纯算法层，不依赖 Django request，可独立测试。
    """

    @classmethod
    def search(cls, cigars, query, stock_only=False, limit=DEFAULT_RESULT_LIMIT):
        """
        对给定雪茄列表进行搜索排序。

        :param cigars: Cigar QuerySet 或 list[Cigar]
        :param query: 搜索字符串
        :param stock_only: 是否只返回有库存的结果（已在 QuerySet 层过滤时设为 False）
        :param limit: 最大返回条数
        :return: list[Cigar] — 排序后的雪茄列表
        """
        if not cigars:
            return []

        # 确保是列表
        cigars = list(cigars)

        # 无查询词时直接截断返回
        if not query or not query.strip():
            return cigars[:limit]

        q_lower = query.lower().strip()
        terms = split_search_terms(query)
        is_multi_term = len(terms) > 1

        scored = []
        for cigar in cigars:
            score = score_cigar(cigar, q_lower, terms, is_multi_term)
            if score >= MIN_SEARCH_SCORE:
                scored.append((cigar, score))

        # 按分数降序排序
        scored.sort(key=lambda x: -x[1])

        # 去重：保留同 (brand, english_name, vitola) 中最高分的
        seen = set()
        deduped = []
        for cigar, _ in scored:
            key = (cigar.brand, cigar.english_name, cigar.vitola)
            if key not in seen:
                seen.add(key)
                deduped.append(cigar)

        return deduped[:limit]
