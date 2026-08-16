export interface GuideStep {
  id: string;
  title: string;
  description: string;
  route: string;
  tourStepId?: string;
}

/** The first-visit guide is deliberately versioned with the application. */
export const GUIDE_STEPS: readonly GuideStep[] = [

  {
    id: 'overview',
    title: '先看懂业务全景',
    description: '库存、销售、账务都围绕同一套雪茄目录和资金账户运转，先花一分钟看懂这张全景图。',
    route: '/',
  },

  {
    id: 'inventory',
    title: '库存与采购',
    description: '在库存页查看现货。每录入一批采购到货，成本和可售数量都会自动带入后面的销售和利润计算。',
    route: '/inventory',
    tourStepId: 'inventory-summary',
  },

  {
    id: 'sales-orders',
    title: '销售单',
    description: '销售单记录客户、商品和金额，后面的出库、收款和利润计算都从它开始。',
    route: '/sales',
    tourStepId: 'sales-orders',
  },

  {
    id: 'fulfillment-payment',
    title: '出库与收款',
    description: '销售单确认后，按实际发生的顺序做出库和收款，库存和资金账户会自动同步。',
    route: '/sales',
    tourStepId: 'sales-fulfillment',
  },

  {
    id: 'accounting',
    title: '账务与对账',
    description: '账务页按资金账户记录每一笔流水，月底用对账把系统余额和手里的实际余额对上。',
    route: '/accounting',
    tourStepId: 'accounting-reconciliation',
  },

  {
    id: 'monthly-profit',
    title: '月利润',
    description: '月利润报表把当月的收入、成本和费用汇总成一张表，一眼看清这个月是赚是亏。',
    route: '/accounting',
    tourStepId: 'accounting-profit',
  },
];

export type ManualChapterCategory = 'quickstart' | 'reference';

export interface ManualSection {
  title: string;
  paragraphs: readonly string[];
  tourStepId?: string;
}

export interface ManualChapter {
  id: string;
  category: ManualChapterCategory;
  title: string;
  summary: string;
  route: string;
  tourStepId?: string;
  sections: readonly ManualSection[];
}

const section = (title: string, ...paragraphs: string[]): ManualSection => ({ title, paragraphs });
const guidedSection = (tourStepId: string, title: string, ...paragraphs: string[]): ManualSection => ({ title, paragraphs, tourStepId });

/** HelpPage 使用的中文手册内容。 */
export const MANUAL_CHAPTERS: readonly ManualChapter[] = [

  {
    id: 'quickstart',
    category: 'quickstart',
    title: '快速开始',
    summary: '用一条最短的路线，走通从入账到月利润的全过程。',
    route: '/',
    tourStepId: 'overview',
    sections: [
      section('工作顺序', '日常记账按这个顺序来：账户入账 → 换汇 → 采购到货 → 库存 → 销售 → 出库收款 → 对账 → 月利润。顺着做，月底汇总会轻松很多。'),
      section('八步快速开始', '第一步，在账户里登记手上的资金；第二步，维护汇率并记录换汇；第三步，采购到货后登记批次和成本；第四步，在库存页确认现货；第五步，开销售单并确认；第六步，按实际顺序做出库和收款；第七步，逐账户对账；第八步，看月利润。'),
      section('常用入口', '顶部导航随时可以去往品牌目录、库存、销售、价格追踪和私密链接。'),
    ],
  },

  {
    id: 'inventory', category: 'reference', title: '库存与采购',
    summary: '现货数量、采购批次和成本，都在库存页查看和管理。', route: '/inventory', tourStepId: 'inventory-summary',
    sections: [
      guidedSection('inventory-summary', '查看库存', '可以按品牌或关键词筛选。销售出库后数量会自动扣减，页面上看到的就是当前现货。'),
      guidedSection('inventory-brand-filter', '按品牌和款式查找', '先选品牌，再输入中文名、英文名或款式关键词。库存表会显示当前支数、成本和最近入库日期。'),
      guidedSection('accounting-actions-purchase', '采购批次', '每次采购先在账务页记录卢布付款，整单到货时系统才创建库存批次。后面算销售成本和利润时用的就是批次成本，不要省略。'),
      section('整盒与散支', '同一款雪茄可以按整盒或散支销售。入库时按实际包装登记，库存页会分别显示盒装和散支的可售数量。'),
    ],
  },

  {
    id: 'day1',
    category: 'quickstart',
    title: '首次 Day 1 初始化',
    summary: '只有第一次建账时需要做这一步：登记四个资金账户和期初库存。完成后不能重来，只能查看。',
    route: '/accounting',
    sections: [
      section('范围与账户', '先选定启用日期，再核对四个账户的余额：我的人民币、合伙人人民币、卢布银行卡和 USDT。余额不能是负数，并且要和手上的实际资金一致。'),
      section('期初库存', '从雪茄目录里挑出手上现有的货，按包装登记：整盒几盒、每盒多少支、散支多少支，再估算每支的人民币成本。这一步只登记现状，不用回头补录过去的采购和换汇。'),
      section('核对生效', '点确认之前，把账户余额、库存成本和期初投入资本都再检查一遍。确认是不可撤销的一步，要么全部生效，要么全部不生效。完成后只能在 /accounting/day1 查看只读摘要。'),
    ],
  },

  {
    id: 'exchange-purchase',
    category: 'quickstart',
    title: '换汇 → 采购',
    summary: '换汇、采购付款、到货入库，按这个顺序记，每一批货的成本才有据可查。',
    route: '/accounting',
    tourStepId: 'accounting-actions-exchange',
    sections: [
      guidedSection('accounting-actions-exchange', '记录换汇', '实际换汇发生后，从人民币或 USDT 公司账户转出，转入卢布银行卡，分别填写实际转出、实际到账和业务日期。系统由两边真实金额计算汇率，不需要先把人民币换成 USDT。'),
      guidedSection('accounting-actions-purchase', '记录采购付款', '打开采购卡，填写实际付款日期，选择实际扣款的卢布银行卡，并写清供应商或批次备注。付款后采购单进入在途，库存不会提前增加。'),
      guidedSection('accounting-purchase-receive', '确认整单到货', '货物一次到齐并核对每款的盒数、每盒支数后，再点击整单到货。本业务不做部分到货；分两次到货时，应拆成两张采购单。'),
      guidedSection('inventory-summary', '确认可售库存', '入库后到库存页核对：数量、包装、成本都对，这批货才算可售。开销售单时只能选有库存的商品。'),
    ],
  },

  {
    id: 'accounting',
    category: 'reference',
    title: '对账 → 月利润',
    summary: '记好人肉成本和日常费用，做完对账，再看这个月赚了多少钱。',
    route: '/accounting',
    tourStepId: 'accounting-reconciliation',
    sections: [
      guidedSection('accounting-actions-expense', '记录实际人肉成本', '订单履约后，按实际花了多少钱记人肉成本。它和客户付的人肉费是两回事：客户付的是收入，实际花的是成本，两笔金额可以不一样。'),
      guidedSection('accounting-actions-expense', '记录日常费用', '工资一般从人民币账户出，房租水电一般从卢布账户出——以实际付款的账户为准，填好日期和备注。费用记在费用里，不要混进销售订单。'),
      guidedSection('accounting-reconciliation', '完成对账', '在 /accounting 的对账区逐个账户核对：系统余额和实际余额对不对得上。有差异就查明原因、处理掉，并写清说明。'),
      guidedSection('accounting-profit-month', '查看月利润', '先选择月份，再核对销售收入、客户人肉费收入、FIFO 销售成本、实际人肉成本和日常费用。退款和冲正进入实际发生的月份。'),
      guidedSection('accounting-actions-dividend', '合伙人分红', '需要分红时，先在账务工作台预览可分配利润，确认无误后再记录本次分红，系统会自动从对应账户扣减。'),
    ],
  },

  {
    id: 'first-order',
    category: 'quickstart',
    title: '完整创建一张销售单',
    summary: '从一张报价开始，走完整张销售单：建草稿、确认预留、出库、收款。',
    route: '/sales',
    tourStepId: 'sales-orders',
    sections: [
      guidedSection('sales-orders', '创建销售草稿', '打开 /sales 后从“新建销售单”开始。完整引导会逐项高亮本节所有字段；它只说明怎么填，不会替你保存、确认、出库或收款。'),
      guidedSection('sales-customer', '填写客户', '填写客户姓名或便于查询的称呼。临时客户可以写“散客”，但同一客户长期交易时应保持名称一致。'),
      guidedSection('sales-transport-payer', '设置人肉费', '先选客户承担还是公司承担。客户承担时填写向客户收取的人民币金额，这笔钱进入订单应收；公司承担时客户人肉费固定为 0，实际成本在履约后另记。'),
      guidedSection('sales-item-search', '从库存添加雪茄', '点击搜索框会显示当前库存，也可以输入中文名、英文名或品牌筛选。点选商品后，再选择整盒或单支；库存不足时保存或确认会被阻止。'),
      guidedSection('sales-item-unit', '填写包装、数量和售价', '整盒销售要核对每盒支数，数量填写盒数；单支销售填写支数。售价一律填写人民币销售单价，不要填卢布采购成本。成本由系统按 FIFO 批次计算。'),
      guidedSection('sales-order-note', '填写备注并保存', '交货约定或报价说明写在备注里。核对商品、数量、售价和应收总额后保存草稿；草稿不会占用库存，也不会产生资金流水。'),
      guidedSection('sales-confirm', '确认并预留', '在订单列表打开刚保存的草稿，再次核对后点击确认。确认后立即预留库存；出库前如客户取消，可用取消动作释放预留。'),
      guidedSection('sales-ship', '按实际日期出库', '货物真正交付时打开已确认订单，点击出库，填写实际交付日期并提交。出库会扣减库存，并固化这张订单使用的 FIFO 批次成本。'),
      guidedSection('sales-receive', '按实际到账记录收款', '客户付款后打开原订单，填写实际到账日期和人民币金额，选择真正收到钱的公司人民币账户，再记录一次性人民币收款。客户先付款也可以先收款后出库。'),
    ],
  },


  {
    id: 'privnote',
    category: 'reference',
    title: '私密链接',
    summary: '为客户生成一次性链接：看库存、付款、读消息或查批发报价。',
    route: '/privnote',
    tourStepId: 'privnote-create',
    sections: [
      guidedSection('privnote-type', '选择类型', '四种类型各有用途：库存链接展示现货和零售价；批发报价链接按当前批发价生成价目表；收款链接关联已有销售单；消息链接发送一次性文字。完整引导默认演示批发报价。'),
      guidedSection('privnote-duration', '设置访问规则', '选择有效期；需要时设置访问密码。开启阅后即焚后，客户第一次查看就会消耗链接，发送前要确认是否需要多次查看。'),
      guidedSection('privnote-quote-mode-full', '选择报价内容', '完整报价使用当前可报价目录；只想发几款时切换定制选择。是否包含运费按与客户的约定设置，并填写客户名称。'),
      guidedSection('privnote-submit', '生成并发送链接', '最后核对客户可见内容，再生成链接并复制发送。查看页不会显示成本、内部账户或其他经营信息。'),
      section('报价实时更新', '批发报价链接在客户打开时按最新的批发价和库存实时生成，之后价格或库存有变动，客户看到的内容也会自动跟着变。'),
    ],
  },

  {
    id: 'prices',
    category: 'reference',
    title: '价格追踪',
    summary: '对比各个拿货渠道的报价，跟踪价格变化。',
    route: '/prices',
    tourStepId: 'prices-dashboard',
    sections: [
      guidedSection('prices-dashboard', '查看报价', '价格页汇总了各个来源的最新报价和库存状态，点进单款雪茄可以看历史价格走势。'),
      guidedSection('prices-filter', '按品牌筛选', '先按品牌缩小范围，再从价格卡片打开单款历史。外部报价用于采购参考，不会自动成为库存成本。'),
      section('价格提醒', '给自己关心的款式设一个目标价，价格到了就能及时跟进市场变化。'),
    ],
  },

  {
    id: 'reversals-audit',
    category: 'reference',
    title: '撤销、退货与库存审计',
    summary: '库存事实不能直接删除；发生错误时按原动作反向处理，并在审计页确认数量和成本仍然一致。',
    route: '/inventory',
    sections: [
      guidedSection('accounting-purchase-reverse-date', '撤销未使用的采购到货', '采购到货录错时，只能撤销一整次到货，而且这批货必须完全没有被预留、出库、拆盒或调整。到采购记录里填写撤销日期和原因，再提交“撤销到货”；系统会保留原到货和反向流水，把批次库存与采购订单退回在途。'),
      guidedSection('sales-return', '整单销售退货后重建', '整单退货只适用于已经出库的订单。先在原销售单执行整单退货，系统按原出库批次和成本恢复库存，并把退款记到原收款科目；再新建一张销售单，不能修改旧单假装没有卖过。实际已经发生的人肉成本不会因为退货被抹掉。'),
      guidedSection('inventory-adjustment-reversal', '撤销整次库存调整', '库存调整撤销必须针对原来那一次完整调整。只要调整后相关批次又发生了入库、预留、出库或其他调整，系统就会阻止撤销，避免把别人的新变化覆盖掉；没有后续变化时选择“撤销调整”即可生成反向流水。'),
      guidedSection('inventory-audit', '运行库存一致性审计', '库存审计是只读检查：逐批比较采购数量、预留、出库、退货、调整和当前可用数量，并同时核对成本守恒。发现异常先暂停新的出库，记录审计结果和订单号，再按对应的撤销或重建流程处理，不要直接改数据库。'),
      section('每种反向操作的边界', '撤销到货、退货和撤销调整都会保留原事实并新增一笔相反流水，重复点击同一个动作应返回同一结果而不会再次扣库存。任何不能明确对应原单、原批次或原调整明细的情况，都先人工核对，不要猜测成本。'),
    ],
  },
];

export function getManualChapter(id: string): ManualChapter | undefined {
  return MANUAL_CHAPTERS.find(chapter => chapter.id === (id === 'sales' ? 'first-order' : id));
}

export function getManualChapterForRoute(route: string): ManualChapter | undefined {
  const [pathname, hash = ''] = route.split('#', 2);
  const normalizedRoute = hash ? `${pathname}#${hash}` : pathname;
  if (normalizedRoute === "/accounting") return MANUAL_CHAPTERS.find(chapter => chapter.id === "accounting");
  if (normalizedRoute === "/sales") return MANUAL_CHAPTERS.find(chapter => chapter.id === "first-order");
  return MANUAL_CHAPTERS.find(chapter => chapter.route === normalizedRoute);
}
