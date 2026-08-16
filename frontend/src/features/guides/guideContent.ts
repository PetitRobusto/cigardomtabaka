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

/** Static, Chinese manual metadata/content consumed by HelpPage. */
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
      section('查看库存', '可以按品牌或关键词筛选。销售出库后数量会自动扣减，页面上看到的就是当前现货。'),
      section('采购批次', '每次采购到货都要登记批次和成本。后面算销售成本和利润时用的就是这里的数据，不要省略。'),
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
    sections: [
      section('记录换汇', '实际换汇发生后，在账务工作台记一笔：从人民币或 USDT 账户转出，转入卢布账户，填好日期和汇率。换汇要记成资金流水，不能只写在备注里。'),
      section('记录采购付款', '用卢布账户记采购付款，写清供应商和金额。等货到了再登记采购批次，这样每一批货的成本都对得上来源。'),
      section('确认可售库存', '入库后到库存页核对：数量、包装、成本都对，这批货才算可售。开销售单时只能选有库存的商品。'),
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
      section('记录实际人肉成本', '订单履约后，按实际花了多少钱记人肉成本。它和客户付的人肉费是两回事：客户付的是收入，实际花的是成本，两笔金额可以不一样。'),
      section('记录日常费用', '工资一般从人民币账户出，房租水电一般从卢布账户出——以实际付款的账户为准，填好日期和备注。费用记在费用里，不要混进销售订单。'),
      section('完成对账', '在 /accounting 的对账区逐个账户核对：系统余额和实际余额对不对得上。有差异就查明原因、处理掉，并写清说明。'),
      section('查看月利润', '对账完成后看月利润。净利润 = 销售收入 + 人肉费收入 − 销售成本 − 实际人肉成本 − 日常费用。'),
      section('合伙人分红', '需要分红时，先在账务工作台预览可分配利润，确认无误后再记录本次分红，系统会自动从对应账户扣减。'),
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
      section('创建销售草稿', '先人工核对报价，再打开 /sales 点“新建销售单”，填客户名称、商品、售价和备注。“保存草稿”只是把单子存下来：不会确认订单、不会占用库存，也不会收款。'),
      section('添加现货', '在“添加雪茄”输入框里输入关键词，列表会列出当前有库存的雪茄；选整盒或散支，填好售价。就算搜索时能选到，保存时如果库存不够，系统也会拦下这张单子。'),
      section('设置人肉费', '在“人肉费承担方”里选由谁承担。选“客户承担”：填向客户收的人肉费（不能为负），这笔钱计入应收。选“公司承担”：向客户收的费用必须为 0，实际产生的人肉成本等履约后再记。'),
      section('确认并预留', '保存草稿后回到 /sales 的订单卡片，确认前再检查一遍商品和金额。只有你亲手点“确认”，系统才会锁定订单并预留库存——页面引导只做演示，不会替你确认。'),
      section('出库与收款', '货什么时候出、钱什么时候到，就按什么顺序操作：先在订单卡片上点出库，再记录一次性人民币收款并选择到账账户。实际人肉成本、对账和利润都在账务工作台处理。'),
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
      section('选择类型', '四种类型各有用途：库存链接展示现货和零售价；批发报价链接按当前批发价生成价目表；收款链接发给客户付款；消息链接用来发一次性的文字消息。'),
      section('发送链接', '创建后把链接复制发给客户。链接是一次性的，客户打开看过即焚，查看页上不会显示任何内部信息。'),
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
      section('查看报价', '价格页汇总了各个来源的最新报价和库存状态，点进单款雪茄可以看历史价格走势。'),
      section('价格提醒', '给自己关心的款式设一个目标价，价格到了就能及时跟进市场变化。'),
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
