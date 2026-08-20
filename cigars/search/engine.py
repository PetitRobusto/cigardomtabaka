"""雪茄搜索引擎 — 零 HTTP 依赖，纯算法层"""
from heapq import nsmallest
from itertools import islice
import re

from cigars.search.scoring import compact_search_text, normalize_search_text, score_cigar
from cigars.search.constants import DEFAULT_RESULT_LIMIT, MIN_SEARCH_SCORE


# 中文连续词与字母/数字型号分开；标点只作为分隔符，不污染搜索词。
SEARCH_TERM_PATTERN = re.compile(r'[\u3400-\u9fff]+|[^\W_]+')


def split_search_terms(q):
    """按 CJK/非 CJK 边界拆分查询词"""
    terms = SEARCH_TERM_PATTERN.findall(normalize_search_text(q))
    return [term for term in terms if term]


def limited_candidates(cigars, limit):
    """空查询只读取需要展示的候选，不物化整个目录。"""
    try:
        candidates = cigars[:limit]
    except TypeError:
        candidates = islice(cigars, limit)
    return list(candidates)


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
        if limit <= 0:
            return []

        # 无查询词时直接截断返回
        if not query or not query.strip():
            return limited_candidates(cigars, limit)

        cigars = list(cigars)
        if not cigars:
            return []

        q_lower = normalize_search_text(query).strip()
        query_compact = compact_search_text(q_lower)
        terms = split_search_terms(q_lower)
        is_multi_term = len(terms) > 1

        best_by_product = {}
        for position, cigar in enumerate(cigars):
            score = score_cigar(
                cigar, q_lower, terms, is_multi_term,
                query_compact=query_compact,
            )
            if score >= MIN_SEARCH_SCORE:
                key = (cigar.brand, cigar.english_name, cigar.vitola)
                previous = best_by_product.get(key)
                if previous is None or score > previous[0]:
                    best_by_product[key] = (score, position, cigar)

        ranked = nsmallest(
            limit,
            best_by_product.values(),
            key=lambda result: (-result[0], result[1]),
        )
        return [cigar for _, _, cigar in ranked]
