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
    route: '/sales#accounting',
    tourStepId: 'accounting-reconciliation',
  },
  {
    id: 'monthly-profit',
    title: '月利润',
    description: '月利润报表汇总销售、成本与费用，帮助你快速判断经营结果。',
    route: '/sales#accounting',
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
    id: 'inventory',
    category: 'reference',
    title: '库存与采购',
    summary: '查看现货、采购批次和成本，掌握可售库存。',
    route: '/inventory',
    tourStepId: 'inventory-summary',
    sections: [
      section('查看库存', '按品牌或关键词筛选库存，库存数量会随销售出库实时变化。'),
      section('采购批次', '采购信息应保留批次和成本，后续销售与利润计算会使用这些数据。'),
    ],
  },
  {
    id: 'sales',
    category: 'reference',
    title: '销售单',
    summary: '创建并推进销售订单，串起出库与收款。',
    route: '/sales',
    tourStepId: 'sales-orders',
    sections: [
      section('创建销售单', '填写客户和商品数量，系统会校验库存并计算订单金额。'),
      section('推进状态', '根据实际业务依次确认、出库、收款；取消或退款也应在订单上操作。'),
    ],
  },
  {
    id: 'accounting',
    category: 'reference',
    title: '账务与对账',
    summary: '管理资金账户、流水和对账，确保账实相符。',
    route: '/sales#accounting',
    tourStepId: 'accounting-reconciliation',
    sections: [
      section('账务概览', '账务面板展示各资金账户余额和业务流水，销售收款会关联到对应账户。'),
      section('对账', '按业务日期录入实际余额并确认差异，保留备注方便后续追溯。'),
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
  return MANUAL_CHAPTERS.find(chapter => chapter.id === id);
}

export function getManualChapterForRoute(route: string): ManualChapter | undefined {
  const [pathname, hash = ''] = route.split('#', 2);
  const normalizedRoute = hash ? `${pathname}#${hash}` : pathname;
  return MANUAL_CHAPTERS.find(chapter => chapter.route === normalizedRoute);
}
