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
    description: '从库存、销售到账务，所有业务都围绕同一套雪茄目录和资金流转展开。',
    route: '/',
  },

  {
    id: 'inventory',
    title: '库存与采购',
    description: '在库存页查看现货，录入采购批次后，成本和可售数量会沿业务链路流转。',
    route: '/inventory',
    tourStepId: 'inventory-summary',
  },

  {
    id: 'sales-orders',
    title: '销售单',
    description: '销售单记录客户、商品和金额，是后续出库、收款及利润计算的起点。',
    route: '/sales',
    tourStepId: 'sales-orders',
  },

  {
    id: 'fulfillment-payment',
    title: '出库与收款',
    description: '确认销售单后处理出库和收款，业务状态与资金账户会保持一致。',
    route: '/sales',
    tourStepId: 'sales-fulfillment',
  },

  {
    id: 'accounting',
    title: '账务与对账',
    description: '账务页按资金账户记录流水，并用对账核对系统金额与实际余额。',
    route: '/accounting',
    tourStepId: 'accounting-reconciliation',
  },

  {
    id: 'monthly-profit',
    title: '月利润',
    description: '月利润报表汇总销售、成本与费用，帮助你快速判断经营结果。',
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
    summary: '用最短路径熟悉目录、库存、销售和账务之间的关系。',
    route: '/',
    tourStepId: 'overview',
    sections: [
      section('工作顺序', '按账户入账、汇率换汇、采购到货、库存、销售、出库与收款、对账、月利润的顺序记录业务，月底汇总会更简单。'),
      section('八步快速开始', '账户先记录资金来源，再维护 FX 汇率和换汇；采购到货形成成本批次，库存确认可售，销售单确认后办理出库与收款，最后完成对账并查看月利润。'),
      section('常用入口', '顶部导航可以随时返回品牌目录、库存、销售、价格和私密链接。'),
    ],
  },

  {
    id: 'inventory', category: 'reference', title: '库存与采购',
    summary: '查看现货、采购批次和成本，掌握可售库存。', route: '/inventory', tourStepId: 'inventory-summary',
    sections: [section('查看库存', '按品牌或关键词筛选库存，库存数量会随销售出库实时变化。'), section('采购批次', '采购信息应保留批次和成本，后续销售与利润计算会使用这些数据。')],
  },

  {
    id: 'day1',
    category: 'quickstart',
    title: '首次 Day 1 初始化',
    summary: '只在首次建账时录入四个公司账户和期初库存；完成后仍可阅读规则，但不能重跑。',
    route: '/accounting/day1',
    tourStepId: 'day1',
    sections: [
      section('范围与账户', '选择启用业务日期，核对我的人民币、合伙人人民币、卢布银行卡和 USDT 四个账户；所有余额与账面成本必须非负且匹配。'),
      section('期初库存', '从雪茄目录选择现有商品，按包装录入整盒、每盒支数、散支和估算每支人民币成本；这里不伪造历史采购或换汇。'),
      section('核对生效', '确认前检查账户、库存成本和期初投入资本。最终确认是一次性原子操作；完成后只能从 /accounting/day1 查看只读摘要。'),
    ],
  },

  {
    id: 'exchange-purchase',
    category: 'quickstart',
    title: '换汇 → 采购',
    summary: '先记录人民币或 USDT 换入卢布，再记录采购付款与到货，最后让批次进入可售库存。',
    route: '/accounting',
    sections: [
      section('记录换汇', '在账务工作台先记录实际换汇：来源账户减少、卢布账户增加，并保存业务日期和汇率；不要用备注代替资金流水。'),
      section('记录采购付款', '以卢布账户记录采购付款，保留供应商和金额；到货后再创建采购批次，让库存成本有明确来源。'),
      section('确认可售库存', '检查批次数量、包装和成本进入库存，销售单只能从有库存的目录项选择。'),
    ],
  },

  {
    id: 'accounting',
    category: 'reference',
    title: '对账 → 月利润',
    summary: '记录实际人肉成本和日常费用，完成对账后查看当月经营结果。',
    route: '/accounting',
    tourStepId: 'accounting-reconciliation',
    sections: [
      section('记录实际人肉成本', '销售履约后，在订单真实动作中按实际发生金额记录人肉成本；它可以与客户承担的人肉费不同。'),
      section('记录日常费用', '工资通常记入人民币账户，房租水电等费用通常记入卢布账户；始终以实际支付账户为准并保留日期和备注，避免用销售订单承载费用。'),
      section('完成对账', '在 /accounting 的对账区域逐账户核对系统余额与实际余额，处理差异并保留说明。'),
      section('查看月利润', '对账完成后查看月利润，收入、人肉费收入、销售成本、人肉实际成本和费用共同决定净利润。'),
    ],
  },

  {
    id: 'first-order',
    category: 'quickstart',
    title: '完整创建一张销售单',
    summary: '从报价信息开始，在真实 /sales 订单中心完成草稿、预留、出库和一次性人民币收款。',
    route: '/sales',
    tourStepId: 'sales-orders',
    sections: [
      section('创建销售草稿', '先把报价信息人工核对后打开 /sales，在“新建销售单”填写客户名称、商品、售价和备注。点击保存草稿只保存订单草稿，不会确认、预留库存或收款。'),
      section('添加现货', '聚焦真实的“添加雪茄”输入框，列表会立即展示有库存的雪茄；选择整盒或散支并填写售价。联想结果只是选择提示，提交时后端仍会重新校验库存。'),
      section('设置人肉费', '在“人肉费承担方”选择客户或公司。客户承担时填写非负客户人肉费并计入应收；公司承担时客户收费必须为 0，实际成本另在履约后记录。'),
      section('确认并预留', '保存草稿后回到 /sales 的订单卡，确认前再次检查商品和金额。只有经营者明确点击真实的确认动作，系统才会冻结订单并预留库存；帮助引导不会替你确认。'),
      section('出库与收款', '按真实发生顺序在订单卡点击出库，再用收款动作记录一次性人民币收款和账户。人肉实际成本、对账和利润在账务工作台完成；引导只导航和聚焦，不调用任何写 API。'),
    ],
  },


  {
    id: 'privnote',
    category: 'reference',
    title: '私密链接',
    summary: '为客户生成库存、收款、消息或批发报价链接。',
    route: '/privnote',
    tourStepId: 'privnote-create',
    sections: [
      section('选择类型', '库存链接用于现货展示，批发报价链接读取当前批发价；收款和消息链接用于单独沟通。'),
      section('发送链接', '创建后复制一次性链接给客户，公开查看页不会显示内部引导。'),
    ],
  },

  {
    id: 'prices',
    category: 'reference',
    title: '价格追踪',
    summary: '对比来源报价与历史价格变化。',
    route: '/prices',
    tourStepId: 'prices-dashboard',
    sections: [
      section('查看报价', '价格页汇总各来源的最新报价和库存状态，可进入单款查看历史。'),
      section('价格提醒', '在提醒页维护目标价格，方便及时跟进市场变化。'),
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
