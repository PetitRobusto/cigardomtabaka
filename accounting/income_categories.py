"""共享业务分类；旧 category 继续用于稳定的会计科目归集。"""
import json
from pathlib import Path

from accounting.services import LedgerError

CATALOG = json.loads((Path(__file__).resolve().parent.parent / 'frontend/src/features/accounting/incomeCatalog.json').read_text())
SUBCATEGORIES = {item['value']: (group, item) for group in CATALOG for item in group['items']}


def validate_income_category(category, subcategory, recognition_confirmed, *, legacy=False):
    if type(recognition_confirmed) is not bool:
        raise LedgerError('收益确认须为布尔值', code='input_error')
    if legacy and subcategory == '' and not recognition_confirmed:
        return
    if not isinstance(subcategory, str) or subcategory not in SUBCATEGORIES:
        raise LedgerError('请选择有效的收入一级分类和二级明细；旧版未入账请求请重新选择后确认', code='invalid_subcategory')
    _, item = SUBCATEGORIES[subcategory]
    if item['category'] != category:
        raise LedgerError('收入明细与会计分类不一致', code='invalid_subcategory')
    if not item['manual_entry_enabled']:
        raise LedgerError(item['notice'], code='income_requires_separate_accounting')
    if item['requires_recognition'] and not recognition_confirmed:
        raise LedgerError('请确认收益已实现并到账、符合该明细条件且未重复入账', code='income_recognition_required')


def classification(income):
    selected = SUBCATEGORIES.get(income.subcategory)
    if selected:
        group, item = selected
        return dict(income_group=group['value'], income_group_label=group['label'],
                    subcategory=income.subcategory, subcategory_label=item['label'])
    group_code = {'interest': 'financial', 'used_item': 'disposal', 'other': 'other'}[income.category]
    group = next(group for group in CATALOG if group['value'] == group_code)
    return dict(income_group=group_code, income_group_label=group['label'],
                subcategory='', subcategory_label=f'{income.get_category_display()}（历史未细分）')
