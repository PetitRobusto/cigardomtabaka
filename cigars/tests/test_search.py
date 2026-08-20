from types import SimpleNamespace

from django.test import SimpleTestCase

from cigars.search.engine import CigarSearchEngine, split_search_terms
from cigars.search.scoring import compute_base_score, normalize_search_text, score_cigar


def cigar(**overrides):
    values = {
        'brand': 'Partagás',
        'name': '帕特加斯 D4',
        'english_name': 'Serie D No. 4',
        'vitola': 'Robusto',
        'vitola_cn': '罗布图',
        'common_name': '',
        'common_name_cn': '',
        'release_type': '',
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class SliceOnlyCandidates:
    def __init__(self, values):
        self.values = values
        self.requested_slice = None

    def __bool__(self):
        raise AssertionError('空查询不应检查并物化完整候选集')

    def __getitem__(self, key):
        self.requested_slice = key
        return self.values[key]


class CigarSearchEngineTest(SimpleTestCase):
    def test_empty_query_slices_candidates_before_materializing(self):
        candidates = SliceOnlyCandidates([cigar(name=str(index)) for index in range(5)])

        results = CigarSearchEngine.search(candidates, '', limit=2)

        self.assertEqual(len(results), 2)
        self.assertEqual(candidates.requested_slice, slice(None, 2))

    def test_multi_word_token_score_uses_word_boundaries(self):
        score = compute_base_score(
            'robusto bolivar',
            'bolivar robusto',
            'bolivarrobusto',
        )

        self.assertEqual(score, 100)

    def test_chinese_query_ignores_punctuation_and_full_width_forms(self):
        target = cigar()
        nearby = cigar(name='帕特加斯 D5', english_name='Serie D No. 5')

        compact = CigarSearchEngine.search([target], '帕特加斯D4')
        punctuated = CigarSearchEngine.search([target], '帕特加斯·Ｄ４')
        fuzzy_typo = CigarSearchEngine.search([nearby, target], '帕特加丝D4')

        self.assertEqual(compact, [target])
        self.assertEqual(punctuated, [target])
        self.assertEqual(fuzzy_typo[0], target)
        self.assertEqual(split_search_terms('帕特加斯·Ｄ４'), ['帕特加斯', 'd4'])
        self.assertEqual(normalize_search_text('Partagás'), 'partagas')

    def test_chinese_brand_and_product_terms_receive_multi_term_bonus(self):
        target = cigar()
        brand_only = score_cigar(target, '帕特加斯', ['帕特加斯'], False)
        brand_and_size = score_cigar(target, '帕特加斯d4', ['帕特加斯', 'd4'], True)

        self.assertGreater(brand_and_size, brand_only)

    def test_exact_chinese_product_name_outranks_a_vitola_only_match(self):
        exact_name = cigar(
            brand='Cohiba', name='罗布图', english_name='Robustos', vitola='Robusto',
        )
        vitola_only = cigar(
            brand='Cohiba', name='小说', english_name='Novedosos', vitola='Robusto',
        )

        results = CigarSearchEngine.search(
            [vitola_only, exact_name], '高希霸 罗布图',
        )

        self.assertEqual(results[0], exact_name)

    def test_english_product_name_outranks_a_vitola_only_match(self):
        exact_name = cigar(
            brand='Cohiba', name='罗布图', english_name='Robustos', vitola='Robusto',
        )
        vitola_only = cigar(
            brand='Cohiba', name='小说', english_name='Novedosos', vitola='Robustos No.2',
        )

        results = CigarSearchEngine.search(
            [vitola_only, exact_name], 'Cohiba Robusto',
        )

        self.assertEqual(results[0], exact_name)

    def test_deduplication_keeps_the_highest_scoring_release(self):
        special = cigar(release_type='Limited Edition Series')
        regular = cigar()

        results = CigarSearchEngine.search([special, regular], 'partagas d4')

        self.assertEqual(results, [regular])
