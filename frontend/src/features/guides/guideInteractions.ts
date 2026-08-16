export type GuideCompletionAction = 'close' | 'skip' | 'finish' | 'escape';

export interface ContextTourStep {
  id: string;
  title: string;
  description: string;
  target: string;
  route: string;
  /** 等待用户完成上一步动作后，动态目标才会出现。 */
  waitForTarget?: boolean;
}

const salesCreateSteps: readonly ContextTourStep[] = [
  { id: 'sales-orders', title: '创建销售单', description: '从这张表单开始。引导只会高亮字段，不会代你保存或确认订单。', target: '[data-guide="sales-orders"]', route: '/sales' },
  { id: 'sales-customer', title: '填写客户', description: '填写客户名称；临时散客也可以写“散客”，方便之后查找订单。', target: '[data-guide="sales-order-customer"]', route: '/sales' },
  { id: 'sales-transport-payer', title: '选择人肉费承担方', description: '客户承担时，人肉费计入应收；公司承担时，客户人肉费自动为 0，实际成本在履约后另记。', target: '[data-guide="sales-order-transport-payer"]', route: '/sales' },
  { id: 'sales-transport-fee', title: '填写客户人肉费', description: '如果选择客户承担，填客户实际要付的人肉费；金额只能是非负数，选择公司承担时这里会锁定为 0。', target: '[data-guide="sales-order-transport-fee"]', route: '/sales' },
  { id: 'sales-item-search', title: '搜索库存商品', description: '点击输入框会加载库存列表。输入中文名、英文名或品牌，再从下拉列表点选一款现货。', target: '[data-guide="sales-order-item-search"]', route: '/sales' },
  { id: 'sales-item-unit', title: '选择销售单位', description: '商品加入后选择整盒或单支；整盒销售还要核对每盒支数。请先在上一步选中商品。', target: '[data-guide="sales-order-item-unit"]', route: '/sales', waitForTarget: true },
  { id: 'sales-item-quantity', title: '填写数量', description: '填写本次销售的盒数或支数，必须大于 0，系统会按包装换算占用库存。', target: '[data-guide="sales-order-item-quantity"]', route: '/sales', waitForTarget: true },
  { id: 'sales-item-price', title: '填写销售单价', description: '填写人民币销售单价，最多两位小数。这里是售价，不要把卢布成本填进来。', target: '[data-guide="sales-order-item-price"]', route: '/sales', waitForTarget: true },
  { id: 'sales-order-note', title: '补充备注', description: '需要交代交货、客户或报价信息时写在备注里；没有内容可以留空。', target: '[data-guide="sales-order-note"]', route: '/sales' },
  { id: 'sales-save-draft', title: '保存销售草稿', description: '确认商品、数量、售价和应收金额后保存。保存草稿不会预留库存，也不会产生收款。', target: '[data-guide="sales-order-save"]', route: '/sales' },
  { id: 'sales-fulfillment', title: '打开订单详情', description: '草稿保存后，在订单列表点击这张订单展开详情，才能看到确认、出库和收款动作。', target: '[data-guide="sales-fulfillment"]', route: '/sales', waitForTarget: true },
  { id: 'sales-confirm', title: '确认并预留库存', description: '再次核对订单后点击确认。确认会按当前库存预留商品；出库前仍可以取消订单。', target: '[data-guide="sales-action-confirm"]', route: '/sales', waitForTarget: true },
];

const salesShipmentSteps: readonly ContextTourStep[] = [
  { id: 'sales-ship', title: '登记出库', description: '货物实际交付时点击出库并填写业务日期。出库会扣减库存并固化本次销售的批次成本。', target: '[data-guide="sales-action-ship"]', route: '/sales', waitForTarget: true },
  { id: 'sales-ship-date', title: '填写出库日期', description: '填写货物实际交付的业务日期，再执行出库。', target: '[data-guide="sales-ship-date"]', route: '/sales', waitForTarget: true },
  { id: 'sales-ship-submit', title: '提交出库', description: '核对日期后执行出库；库存和本次批次成本会在这一步固化。', target: '[data-guide="sales-ship-submit"]', route: '/sales', waitForTarget: true },
];

const salesReceiptSteps: readonly ContextTourStep[] = [
  { id: 'sales-receive', title: '记录人民币收款', description: '客户实际付款后点击收款；一张订单只记录一次收款，并选择实际到账的人民币账户。', target: '[data-guide="sales-action-receive"]', route: '/sales', waitForTarget: true },
  { id: 'sales-receive-date', title: '填写收款日期', description: '填写实际到账的业务日期，不能用预计收款日代替。', target: '[data-guide="sales-receive-date"]', route: '/sales', waitForTarget: true },
  { id: 'sales-receive-amount', title: '填写收款金额', description: '填写客户实际支付的人民币金额；通常等于订单应收，但以银行实际到账为准。', target: '[data-guide="sales-receive-amount"]', route: '/sales', waitForTarget: true },
  { id: 'sales-receive-account', title: '选择到账账户', description: '选择实际收到人民币的公司账户。两个合伙人的账户都属于公司，但不能混入个人资金。', target: '[data-guide="sales-receive-account"]', route: '/sales', waitForTarget: true },
  { id: 'sales-receive-submit', title: '提交收款', description: '核对日期、金额和账户后执行收款。收款会增加对应人民币账户余额，月利润按订单收入统计。', target: '[data-guide="sales-action-submit"]', route: '/sales', waitForTarget: true },
];

const salesReturnSteps: readonly ContextTourStep[] = [
  { id: 'sales-return', title: '发起整单退货', description: '只有已出库订单才能整单退货。打开原订单后选择退货，系统会按原批次恢复库存，之后再新建销售单。', target: '[data-guide="sales-action-return"]', route: '/sales', waitForTarget: true },
  { id: 'sales-return-date', title: '填写退货日期', description: '填写客户实际退回货物的业务日期；退货影响发生当月的利润。', target: '[data-guide="sales-return-date"]', route: '/sales', waitForTarget: true },
  { id: 'sales-return-reason', title: '填写退货原因', description: '简短写明整单退货原因，保留原销售事实和后续重建的依据。', target: '[data-guide="sales-return-reason"]', route: '/sales', waitForTarget: true },
  { id: 'sales-return-submit', title: '提交整单退货', description: '核对日期和原因后提交。原订单不会删除，退款和库存反向流水会保留。', target: '[data-guide="sales-return-submit"]', route: '/sales', waitForTarget: true },
];

const accountingExchangeSteps: readonly ContextTourStep[] = [
  { id: 'accounting-actions-exchange', title: '开始记录换汇', description: '先确认这是人民币或 USDT 换入卢布的实际交易，再逐项填写以下字段。', target: '[data-guide="accounting-actions-exchange"]', route: '/accounting' },
  { id: 'accounting-exchange-source-account', title: '选择转出账户', description: '选择实际转出人民币或 USDT 的公司账户。', target: '[data-guide="accounting-exchange-source-account"]', route: '/accounting' },
  { id: 'accounting-exchange-source-amount', title: '填写转出金额', description: '填银行卡或钱包实际转出的原币金额。', target: '[data-guide="accounting-exchange-source-amount"]', route: '/accounting' },
  { id: 'accounting-exchange-rub-account', title: '选择卢布账户', description: '选择实际收到卢布的公司银行卡账户。', target: '[data-guide="accounting-exchange-rub-account"]', route: '/accounting' },
  { id: 'accounting-exchange-rub-amount', title: '填写转入金额', description: '填实际到账的卢布数量，汇率由两边实际数量体现。', target: '[data-guide="accounting-exchange-rub-amount"]', route: '/accounting' },
  { id: 'accounting-exchange-date', title: '填写换汇日期', description: '使用实际换汇发生的业务日期。', target: '[data-guide="accounting-exchange-date"]', route: '/accounting' },
  { id: 'accounting-exchange-submit', title: '提交换汇', description: '核对两边账户和金额后记录换汇，系统会同步资金余额和卢布成本。', target: '[data-guide="accounting-exchange-submit"]', route: '/accounting' },
];

const accountingPurchaseSteps: readonly ContextTourStep[] = [
  { id: 'accounting-actions-purchase', title: '开始记录采购', description: '采购卡按一张采购单操作：先付款，货物一次到齐后再整单到货。', target: '[data-guide="accounting-actions-purchase"]', route: '/accounting' },
  { id: 'accounting-purchase-date', title: '填写采购业务日期', description: '付款或到货时使用实际发生日期；不要用预计日期。', target: '[data-guide="accounting-purchase-date"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-purchase-account', title: '选择卢布付款账户', description: '付款只从启用的卢布账户扣除，选择实际转出的账户。', target: '[data-guide="accounting-purchase-account"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-purchase-note', title: '填写采购备注', description: '写供应商、批次或核对信息，方便以后查成本来源。', target: '[data-guide="accounting-purchase-note"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-purchase-pay', title: '提交采购付款', description: '核对金额、日期和卢布账户后付款；付款不会代替到货入库。', target: '[data-guide="accounting-purchase-pay"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-purchase-receive', title: '提交整单到货', description: '货物一次到齐且包装数量已核对后整单到货，系统才创建库存批次。', target: '[data-guide="accounting-purchase-receive"]', route: '/accounting', waitForTarget: true },
];

const accountingPurchaseReverseSteps: readonly ContextTourStep[] = [
  { id: 'accounting-purchase-reverse-date', title: '填写撤销日期', description: '使用实际发现并撤销错误到货的业务日期。', target: '[data-guide="accounting-purchase-reverse-date"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-purchase-reverse-reason', title: '填写撤销原因', description: '说明原到货哪里录错。原因不能为空，便于之后核对原单和反向流水。', target: '[data-guide="accounting-purchase-reverse-reason"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-purchase-reverse-submit', title: '提交撤销到货', description: '确认整批货完全未使用后提交。系统保留原到货，并把采购单恢复为在途。', target: '[data-guide="accounting-purchase-reverse-submit"]', route: '/accounting', waitForTarget: true },
];

const accountingExpenseSteps: readonly ContextTourStep[] = [
  { id: 'accounting-actions-expense', title: '开始记录经营费用', description: '费用按实际付款账户记录，工资通常走人民币，房租水电通常走卢布。', target: '[data-guide="accounting-actions-expense"]', route: '/accounting' },
  { id: 'accounting-expense-category', title: '选择费用类别', description: '先选工资、房租、水电或其他经营费用，月利润会按类别汇总。', target: '[data-guide="accounting-expense-category"]', route: '/accounting' },
  { id: 'accounting-expense-account', title: '选择费用账户', description: '选择实际付款的公司账户，不能混入个人资金。', target: '[data-guide="accounting-expense-account"]', route: '/accounting' },
  { id: 'accounting-expense-amount', title: '填写费用金额', description: '按账户币种填写实际支付金额，不要换算后再填。', target: '[data-guide="accounting-expense-amount"]', route: '/accounting' },
  { id: 'accounting-expense-date', title: '填写费用日期', description: '使用实际付款日期，月度费用才会归入正确月份。', target: '[data-guide="accounting-expense-date"]', route: '/accounting' },
  { id: 'accounting-expense-note', title: '填写费用备注', description: '写清月份、收款方或用途，便于两位合伙人对账。', target: '[data-guide="accounting-expense-note"]', route: '/accounting' },
  { id: 'accounting-expense-submit', title: '提交费用', description: '核对分类、账户、金额和日期后记录费用。', target: '[data-guide="accounting-expense-submit"]', route: '/accounting' },
];

const accountingDividendSteps: readonly ContextTourStep[] = [
  { id: 'accounting-actions-dividend', title: '开始处理分红', description: '先创建草稿，再填写两位合伙人的金额和账户，预览后才确认。', target: '[data-guide="accounting-actions-dividend"]', route: '/accounting' },
  { id: 'accounting-dividend-total', title: '填写分红总额', description: '填本次准备分出的人民币总额，不能超过可分配利润。', target: '[data-guide="accounting-dividend-total"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-dividend-date', title: '填写分红日期', description: '使用实际分红业务日期。', target: '[data-guide="accounting-dividend-date"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-dividend-create', title: '创建分红草稿', description: '先保存草稿，草稿本身不会扣款。', target: '[data-guide="accounting-dividend-create"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-dividend-partner-a', title: '填写合伙人 A 金额', description: '按本次约定填写 A 的人民币分红金额。', target: '[data-guide="accounting-dividend-partner-a"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-dividend-partner-b', title: '填写合伙人 B 金额', description: '按本次约定填写 B 的人民币分红金额，两人合计应等于总额。', target: '[data-guide="accounting-dividend-partner-b"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-dividend-account-a', title: '选择 A 的账户', description: '选择 A 实际收款的人民币账户。', target: '[data-guide="accounting-dividend-account-a"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-dividend-account-b', title: '选择 B 的账户', description: '选择 B 实际收款的另一个人民币账户。', target: '[data-guide="accounting-dividend-account-b"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-dividend-save', title: '保存分红编辑', description: '金额和账户都填好后先保存编辑，再进行预览。', target: '[data-guide="accounting-dividend-save"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-dividend-preview', title: '预览分红', description: '预览会显示可分配利润和本次金额，确认数据仍是当前版本。', target: '[data-guide="accounting-dividend-preview"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-dividend-confirm', title: '确认分红', description: '最后核对预览结果后确认，系统才会从两个人民币账户记出分红。', target: '[data-guide="accounting-dividend-confirm"]', route: '/accounting', waitForTarget: true },
];

const accountingReconciliationSteps: readonly ContextTourStep[] = [
  { id: 'accounting-reconciliation', title: '进入账户对账', description: '先创建实际余额快照，再逐条确认，不能只看系统余额。', target: '[data-guide="accounting-reconciliation"]', route: '/accounting' },
  { id: 'accounting-reconciliation-open', title: '开始一次对账', description: '点击新增对账，按实际账户余额创建一条待确认记录。', target: '[data-guide="accounting-reconciliation-open"]', route: '/accounting' },
  { id: 'accounting-reconciliation-account', title: '选择对账账户', description: '逐个选择公司账户核对，不把两个人民币账户合并填写。', target: '[data-guide="accounting-reconciliation-account"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-reconciliation-date', title: '填写对账日期', description: '填写你实际查看银行卡或钱包余额的日期。', target: '[data-guide="accounting-reconciliation-date"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-reconciliation-actual', title: '填写实际余额', description: '按账户原币填写实际余额，系统会自动计算与账面余额的差额。', target: '[data-guide="accounting-reconciliation-actual"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-reconciliation-note', title: '说明差异', description: '存在差异时写明已知原因或待查事项；没有差异也可写核对依据。', target: '[data-guide="accounting-reconciliation-note"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-reconciliation-submit', title: '保存对账记录', description: '核对账户、日期和实际余额后保存，先不要跳过未查明的差异。', target: '[data-guide="accounting-reconciliation-submit"]', route: '/accounting', waitForTarget: true },
  { id: 'accounting-reconciliation-confirm', title: '确认对账完成', description: '差异处理清楚后再确认，对账记录会保留当时的账面与实际余额。', target: '[data-guide="accounting-reconciliation-confirm"]', route: '/accounting', waitForTarget: true },
];

const accountingProfitSteps: readonly ContextTourStep[] = [
  { id: 'accounting-profit-month', title: '选择利润月份', description: '选择要结算的月份。退款、费用和冲正按各自实际发生月份进入报表。', target: '[data-guide="accounting-profit-month"]', route: '/accounting' },
  { id: 'accounting-profit', title: '查看月利润', description: '先选择月份，再核对收入、批次成本、人肉成本和经营费用。退款与冲正会按实际发生月份体现。', target: '[data-guide="accounting-profit"]', route: '/accounting' },
];

export const CONTEXT_TOUR_GROUPS: Readonly<Record<string, readonly ContextTourStep[]>> = {
  salesCreate: salesCreateSteps,
  salesShipment: salesShipmentSteps,
  salesReceipt: salesReceiptSteps,
  salesReturn: salesReturnSteps,
  accountingExchange: accountingExchangeSteps,
  accountingPurchase: accountingPurchaseSteps,
  accountingPurchaseReverse: accountingPurchaseReverseSteps,
  accountingExpense: accountingExpenseSteps,
  accountingDividend: accountingDividendSteps,
  accountingReconciliation: accountingReconciliationSteps,
  accountingProfit: accountingProfitSteps,
  overview: [
    { id: 'overview', title: '业务总览', description: '先从这里确认今天要做的是库存、销售还是账务。顶部入口分别进入对应工作台，数据会共享同一套雪茄目录和资金账户。', target: '[data-guide="overview"]', route: '/' },
    { id: 'overview-stats', title: '查看目录摘要', description: '先看品牌总数和目录状态，再决定是否进入库存或价格页继续核对。', target: '[data-guide="overview-stats"]', route: '/' },
    { id: 'overview-brand-search', title: '搜索品牌', description: '输入中文或英文品牌名快速缩小目录范围。', target: '[data-guide="overview-brand-search"]', route: '/' },
    { id: 'overview-brand-list', title: '打开业务入口', description: '品牌卡片进入目录详情；库存、销售和账务请使用顶部导航，跨路由入口不在本次总览引导中连续执行。', target: '[data-guide="overview-brand-list"]', route: '/' },
  ],
  inventoryBrowse: [
    { id: 'inventory-summary', title: '库存概览', description: '先确认品牌、款式、总支数和总成本，再开始筛选。', target: '[data-guide="inventory-summary"]', route: '/inventory' },
    { id: 'inventory-stats', title: '核对库存统计', description: '盘点时先核对总数量和总成本，异常时不要直接改数据库。', target: '[data-guide="inventory-stats"]', route: '/inventory' },
    { id: 'inventory-filters', title: '使用库存筛选', description: '品牌筛选和关键词搜索可以组合使用，清除筛选后回到全量库存。', target: '[data-guide="inventory-filters"]', route: '/inventory' },
    { id: 'inventory-brand-filter', title: '按品牌筛选', description: '选择一个品牌，只查看该品牌的库存和成本。', target: '[data-guide="inventory-brand-filter"]', route: '/inventory' },
    { id: 'inventory-search', title: '搜索库存款式', description: '输入款式关键词，核对当前可售数量和成本均价。', target: '[data-guide="inventory-search"]', route: '/inventory' },
    { id: 'inventory-table', title: '查看库存表', description: '库存表按款式展示数量、成本和最近入库日期，销售出库后会自动更新。', target: '[data-guide="inventory-table"]', route: '/inventory' },
  ],
  inventoryAudit: [
    { id: 'inventory-audit', title: '打开只读库存审计', description: '审计只比较批次数量、成本和流水，不会自动修正数据。', target: '[data-guide="inventory-audit"]', route: '/inventory' },
    { id: 'inventory-audit-run', title: '运行一致性审计', description: '确认没有正在提交的库存动作后运行审计，等待结果返回。', target: '[data-guide="inventory-audit-run"]', route: '/inventory' },
    { id: 'inventory-audit-result', title: '阅读审计结果', description: '通过表示数量和成本一致；发现问题时暂停相关出库，按原始订单追查。', target: '[data-guide="inventory-audit-result"]', route: '/inventory', waitForTarget: true },
  ],
  inventoryAdjustmentReverse: [
    { id: 'inventory-adjustment-reversal', title: '查看最近库存调整', description: '这里只显示近期调整及其是否允许撤销；已有后续变化的调整不能强行撤回。', target: '[data-guide="inventory-adjustment-reversal"]', route: '/inventory', waitForTarget: true },
    { id: 'inventory-adjustment-date', title: '填写撤销日期', description: '使用实际撤销发生日期。', target: '[data-guide="inventory-adjustment-date"]', route: '/inventory', waitForTarget: true },
    { id: 'inventory-adjustment-reason', title: '填写撤销原因', description: '写清为什么撤销，不能留空或猜测原调整内容。', target: '[data-guide="inventory-adjustment-reason"]', route: '/inventory', waitForTarget: true },
    { id: 'inventory-adjustment-submit', title: '提交撤销调整', description: '核对日期和原因后提交，系统保留原调整并新增反向流水。', target: '[data-guide="inventory-adjustment-submit"]', route: '/inventory', waitForTarget: true },
  ],
  privnoteQuote: [
    { id: 'privnote-create', title: '创建私密链接', description: '默认从报价单开始；引导只高亮字段，不会替你生成或发送链接。', target: '[data-guide="privnote-create"]', route: '/privnote' },
    { id: 'privnote-type', title: '选择链接类型', description: '报价用于给客户看价格，收款用于已有销售单，消息用于发送文字或附件；本次默认走报价流程。', target: '[data-guide="privnote-type"]', route: '/privnote' },
    { id: 'privnote-duration', title: '设置有效期', description: '按需要选择链接有效期，短期报价建议不要长期保留。', target: '[data-guide="privnote-duration"]', route: '/privnote' },
    { id: 'privnote-password', title: '设置访问密码', description: '需要额外保护时填写密码；不需要时可以留空。', target: '[data-guide="privnote-password"]', route: '/privnote' },
    { id: 'privnote-burn', title: '选择阅后即焚', description: '开启后客户第一次查看即销毁链接，请在发送前确认是否需要保留查看机会。', target: '[data-guide="privnote-burn"]', route: '/privnote' },
    { id: 'privnote-quote-mode-full', title: '选择完整报价', description: '完整目录会包含当前可报价商品；需要挑选款式时再切换到定制选择。', target: '[data-guide="privnote-quote-mode-full"]', route: '/privnote' },
    { id: 'privnote-shipping', title: '选择是否含运费', description: '客户承担运费时关闭，报价包含人肉/运费时按实际约定开启。', target: '[data-guide="privnote-shipping"]', route: '/privnote' },
    { id: 'privnote-customer', title: '填写客户名称', description: '客户名称会显示在链接内容中，可写客户姓名或称呼。', target: '[data-guide="privnote-customer"]', route: '/privnote' },
    { id: 'privnote-submit', title: '生成私密链接', description: '最后确认类型、有效期和客户可见内容，再生成链接并复制发送。', target: '[data-guide="privnote-submit"]', route: '/privnote' },
  ],
  pricesBrowse: [
    { id: 'prices-dashboard', title: '价格追踪总览', description: '先看当前价格数据是否加载完成，再按品牌筛选。', target: '[data-guide="prices-dashboard"]', route: '/prices' },
    { id: 'prices-stats', title: '查看价格统计', description: '统计显示价格条目、款式、品牌和来源数量，用来判断数据覆盖范围。', target: '[data-guide="prices-stats"]', route: '/prices' },
    { id: 'prices-filter', title: '筛选品牌', description: '选择品牌查看该品牌的价格卡片，点“全部品牌”恢复全量。', target: '[data-guide="prices-filter"]', route: '/prices' },
    { id: 'prices-list', title: '打开单款价格', description: '点击一张价格卡进入单款详情；详情页的历史筛选和图表是另一条路由引导。', target: '[data-guide="prices-list"]', route: '/prices' },
  ],
  pricesDetail: [
    { id: 'prices-history-filter', title: '选择历史范围', description: '先选择 7、14、30 或 90 天，决定历史数据的时间范围。', target: '[data-guide="prices-history-filter"]', route: '/prices/cigar' },
    { id: 'prices-history-table', title: '查看来源历史', description: '对比各来源、包装和库存状态，判断当前报价是否可用。', target: '[data-guide="prices-history-table"]', route: '/prices/cigar', waitForTarget: true },
    { id: 'prices-history-chart', title: '查看价格趋势', description: '用趋势图观察近期价格变化，不把外部报价直接当作采购成本。', target: '[data-guide="prices-history-chart"]', route: '/prices/cigar', waitForTarget: true },
  ],
};

export const CONTEXT_TOUR_STEPS: readonly ContextTourStep[] = Object.values(CONTEXT_TOUR_GROUPS).flat();
export const GUIDE_TARGETS = Object.fromEntries(CONTEXT_TOUR_STEPS.map(step => [step.id, step.target])) as Record<string, string>;

export function completionForAction(action: GuideCompletionAction): { complete: boolean; open: boolean } {
  void action;
  return { complete: true, open: false };
}

export type GuideActionScope = 'welcome' | 'context';

export function guideActionPlan(_action: GuideCompletionAction, scope: GuideActionScope): { requiresPersistence: boolean; close: boolean } {
  return { requiresPersistence: scope === 'welcome', close: true };
}

export function createGuideActionRunner(complete: () => Promise<unknown>) {
  let busy = false;
  return {
    isBusy: () => busy,
    run: async (_action: GuideCompletionAction, onError?: (error: Error) => void): Promise<boolean> => {
      if (busy) return false;
      busy = true;
      try { await complete(); return true; }
      catch (error) { onError?.(error instanceof Error ? error : new Error('引导状态保存失败')); return false; }
      finally { busy = false; }
    },
  };
}

export function missingTargetAction(): { complete: false; open: false; error: string } {
  return { complete: false, open: false, error: '当前页面暂时无法播放本页引导，请刷新后重试。' };
}

/** 提交动作可能移除原按钮；目标曾出现过即可继续。 */
export function canAdvanceTourStep(targetFound: boolean, targetSeen: boolean): boolean {
  return targetFound || targetSeen;
}

function routeMatches(stepRoute: string, pathname: string): boolean {
  if (stepRoute === '/prices/cigar') return pathname.startsWith('/prices/cigar/');
  return stepRoute === pathname;
}

/** Help 只按已注册步骤跳转，避免把账务或库存引导误送到销售页。 */
export function tourStepRoute(id: string): string | null {
  return CONTEXT_TOUR_STEPS.find(step => step.id === id)?.route ?? null;
}

export function tourStepsForRoute(route: string, id?: string): readonly ContextTourStep[] {
  const pathname = route.split('#', 1)[0];
  const routeGroups = Object.values(CONTEXT_TOUR_GROUPS)
    .filter(steps => steps.length > 0 && steps.every(step => routeMatches(step.route, pathname)));
  if (!id) return routeGroups[0] ?? [];
  const steps = routeGroups.find(group => group.some(step => step.id === id));
  if (!steps) return [];
  return steps.slice(steps.findIndex(step => step.id === id));
}

export function resolveTourTarget(id: string, availableSelectors: readonly string[]): string | null {
  const step = CONTEXT_TOUR_STEPS.find(item => item.id === id);
  if (!step || !availableSelectors.includes(step.target)) return null;
  return step.target;
}

export function isGuideExcludedRoute(pathname: string): boolean {
  return pathname === '/login' || pathname.startsWith('/p/');
}
