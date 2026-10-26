import type { StoreLocale } from '../../storefront/types';

export const notFoundCopy = {
  zh: {
    title: '404 · 页面未找到 | CigarDomTabaka',
    heading: '页面未找到',
    message: '请检查链接，或回到商品目录继续浏览。',
    catalog: '浏览商品', home: '返回首页', contact: '联系门店', city: '莫斯科',
    navigation: '返回商城',
  },
  ru: {
    title: '404 · Страница не найдена | CigarDomTabaka',
    heading: 'Страница не найдена',
    message: 'Проверьте адрес или вернитесь в каталог, чтобы продолжить выбор.',
    catalog: 'Перейти в каталог', home: 'На главную', contact: 'Связаться с магазином', city: 'Москва',
    navigation: 'Вернуться в магазин',
  },
  en: {
    title: '404 · Page not found | CigarDomTabaka',
    heading: 'Page not found',
    message: 'Check the link, or return to the catalogue to keep browsing.',
    catalog: 'Browse catalogue', home: 'Back to home', contact: 'Contact the shop', city: 'Moscow',
    navigation: 'Return to the shop',
  },
} satisfies Record<StoreLocale, Record<string, string>>;

export function localeForPath(path: string): StoreLocale {
  const segment = path.split(/[/?#]/)[1];
  return segment === 'ru' || segment === 'en' ? segment : 'zh';
}
