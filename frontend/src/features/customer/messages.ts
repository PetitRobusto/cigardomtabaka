export type CustomerLocale = 'zh' | 'en' | 'ru';

export const languageNames: Record<CustomerLocale, string> = { en: 'English', ru: 'Русский', zh: '简体中文' };
export const languageOptions: CustomerLocale[] = ['ru', 'en', 'zh'];

const zh = {
  language: '语言', brands: '品牌', home: '首页', login: '登录', logout: '退出',
  navigation: '应用导航', mobileNavigation: '移动应用导航', openMenu: '打开导航菜单',
  catalogTitle: '古巴雪茄目录', completeCollection: '完整收录', searchBrands: '搜索品牌名称…',
  loadingBrands: '加载品牌数据…', loadingBrand: '加载品牌详情…', loading: '页面内容加载中…',
  loadError: '数据加载失败', retry: '重新加载', noBrands: '暂无品牌数据',
  waitingForData: '等待数据抓取完成后自动显示', noMatchingBrands: '未找到匹配品牌', trySearch: '请尝试其他搜索词',
  brandNotFound: '品牌不存在', searchCigars: '搜索雪茄名称…', filter: '筛选',
  all: '全部', regular: '常规', limited: '限量', regional: '地区限定', regionalBadge: '地限', special: '特别',
  noMatchingCigars: '未找到匹配雪茄', tryFilters: '请尝试其他搜索词或筛选条件',
  cuba: '古巴', havana: '哈瓦那', global: '全球', value: '价值', volume: '走量', series: '系列', cigarUnit: '款雪茄', ringGauge: '环径',
  storeTagline: '专业、正品、平价', storeCredential: '莫斯科持证雪茄服务商',
  storeQualification: '专业门店资质', certifiedRetailer: '认证零售商', copyright: '版权所有。',
  storeAddress: '门店地址', storeHours: '营业时间', storePhone: '电话', storeWechat: '微信', storeSocial: '在线联系', storeMap: '门店位置地图', storeMapOpen: '在 Yandex 地图中打开',
  ageKicker: '年龄确认', ageTitle: '是否已满18岁？',
  ageBody: '本站内容涉及烟草制品，仅向成年访客开放。请确认您已年满18周岁。',
  ageYes: '是的，我已满18岁', ageNo: '未满18岁', ageNote: '您可以随时通过顶部入口切换语言。',
  deniedTitle: '抱歉，内容暂不可访问', deniedBody: '本站内容仅面向年满18岁的访客，感谢您的理解。',
  ageBack: '返回年龄确认',
};

type Messages = Record<keyof typeof zh, string>;
export const customerMessages: Record<CustomerLocale, Messages> = {
  zh,
  en: {
    language: 'Language', brands: 'Brands', home: 'Home', login: 'Log in', logout: 'Log out',
    navigation: 'Site navigation', mobileNavigation: 'Mobile navigation', openMenu: 'Open navigation menu',
    catalogTitle: 'Cuban Cigar Catalogue', completeCollection: 'Complete collection', searchBrands: 'Search brand names…',
    loadingBrands: 'Loading brands…', loadingBrand: 'Loading brand details…', loading: 'Loading page…',
    loadError: 'Could not load data', retry: 'Reload', noBrands: 'No brands yet',
    waitingForData: 'The catalogue will appear when data is available.', noMatchingBrands: 'No matching brands', trySearch: 'Try another search term',
    brandNotFound: 'Brand not found', searchCigars: 'Search cigar names…', filter: 'Filter',
    all: 'All', regular: 'Regular', limited: 'Limited', regional: 'Regional', regionalBadge: 'Regional', special: 'Special',
    noMatchingCigars: 'No matching cigars', tryFilters: 'Try another search term or filter',
    cuba: 'Cuba', havana: 'Havana', global: 'Global', value: 'Value', volume: 'Volume', series: 'Series', cigarUnit: 'Cigars', ringGauge: 'ring gauge',
    storeTagline: 'Expertise · Authenticity · Fair prices', storeCredential: 'Licensed cigar specialist in Moscow',
    storeQualification: 'Specialist retailer credentials', certifiedRetailer: 'Certified Retailer', copyright: 'All rights reserved.',
    storeAddress: 'Visit us', storeHours: 'Opening hours', storePhone: 'Phone', storeWechat: 'WeChat', storeSocial: 'Messengers', storeMap: 'Store location map', storeMapOpen: 'Open in Yandex Maps',
    ageKicker: 'Age confirmation', ageTitle: 'Are you 18 or older?',
    ageBody: 'This site covers tobacco products and is intended for adult visitors only. Please confirm that you are at least 18 years old.',
    ageYes: 'Yes, I am 18 or older', ageNo: 'I am under 18', ageNote: 'You can change the language at the top of this page.',
    deniedTitle: 'Content not available', deniedBody: 'This site is intended for visitors aged 18 and over. Thank you for your understanding.',
    ageBack: 'Back to age confirmation',
  },
  ru: {
    language: 'Язык', brands: 'Бренды', home: 'Главная', login: 'Войти', logout: 'Выйти',
    navigation: 'Навигация сайта', mobileNavigation: 'Мобильная навигация', openMenu: 'Открыть меню',
    catalogTitle: 'Каталог кубинских сигар', completeCollection: 'Полная коллекция', searchBrands: 'Поиск по названию бренда…',
    loadingBrands: 'Загрузка брендов…', loadingBrand: 'Загрузка информации о бренде…', loading: 'Загрузка страницы…',
    loadError: 'Не удалось загрузить данные', retry: 'Повторить', noBrands: 'Брендов пока нет',
    waitingForData: 'Каталог появится, когда данные будут доступны.', noMatchingBrands: 'Бренды не найдены', trySearch: 'Попробуйте другой запрос',
    brandNotFound: 'Бренд не найден', searchCigars: 'Поиск сигар…', filter: 'Фильтр',
    all: 'Все', regular: 'Регулярные', limited: 'Лимитированные', regional: 'Региональные', regionalBadge: 'Региональная', special: 'Специальная',
    noMatchingCigars: 'Сигары не найдены', tryFilters: 'Попробуйте другой запрос или фильтр',
    cuba: 'Куба', havana: 'Гавана', global: 'Глобальный', value: 'Доступный', volume: 'Массовый', series: 'Серии', cigarUnit: 'Сигары', ringGauge: 'ринг гейдж',
    storeTagline: 'Профессионализм · Подлинность · Доступные цены', storeCredential: 'Лицензированный сигарный магазин в Москве',
    storeQualification: 'Сертифицированный специализированный магазин', certifiedRetailer: 'Сертифицированный ритейлер', copyright: 'Все права защищены.',
    storeAddress: 'Адрес магазина', storeHours: 'Часы работы', storePhone: 'Телефон', storeWechat: 'WeChat', storeSocial: 'Мессенджеры', storeMap: 'Карта расположения магазина', storeMapOpen: 'Открыть в Яндекс Картах',
    ageKicker: 'Подтверждение возраста', ageTitle: 'Вам уже исполнилось 18 лет?',
    ageBody: 'Сайт посвящён табачным изделиям и предназначен только для совершеннолетних посетителей. Подтвердите, что вам исполнилось 18 лет.',
    ageYes: 'Да, мне есть 18 лет', ageNo: 'Мне нет 18 лет', ageNote: 'Язык можно изменить в верхней части страницы.',
    deniedTitle: 'Доступ ограничен', deniedBody: 'Сайт предназначен для посетителей от 18 лет. Спасибо за понимание.',
    ageBack: 'Вернуться к подтверждению',
  },
};

const categories: Record<string, Record<CustomerLocale, string>> = {
  global: { zh: '全球品牌', en: 'Global brands', ru: 'Глобальные бренды' },
  value: { zh: '价值品牌', en: 'Value brands', ru: 'Доступные бренды' },
  volume: { zh: '走量品牌', en: 'Volume brands', ru: 'Массовые бренды' },
  other: { zh: '其他品牌', en: 'Other brands', ru: 'Другие бренды' },
  ict: { zh: 'ICT 机制', en: 'ICT machine-made', ru: 'ICT · Машинное производство' },
  special: { zh: '特殊品牌', en: 'Special brands', ru: 'Специальные бренды' },
  discontinued: { zh: '已停产品牌', en: 'Discontinued brands', ru: 'Бренды, снятые с производства' },
};

export function brandCategoryLabel(key: string, original: string, locale: CustomerLocale): string {
  return locale === 'zh' ? original : categories[key]?.[locale] ?? original;
}

export function catalogCount(count: number, kind: 'brands' | 'cigars', locale: CustomerLocale): string {
  if (locale === 'zh') return `${count} ${kind === 'brands' ? '个品牌' : '款雪茄'}`;
  if (locale === 'en') return `${count} ${kind === 'brands' ? 'brand' : 'cigar'}${count === 1 ? '' : 's'}`;
  const form = new Intl.PluralRules('ru').select(count);
  const words = kind === 'brands' ? ['бренд', 'бренда', 'брендов'] : ['сигара', 'сигары', 'сигар'];
  return `${count} ${words[form === 'one' ? 0 : form === 'few' ? 1 : 2]}`;
}
