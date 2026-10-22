import { useEffect } from 'react';
import { useCustomerExperience } from './useCustomerExperience';

export default function CustomerDocumentLanguage() {
  const { locale } = useCustomerExperience();
  useEffect(() => {
    document.documentElement.lang = locale === 'zh' ? 'zh-CN' : locale;
  }, [locale]);
  return null;
}
