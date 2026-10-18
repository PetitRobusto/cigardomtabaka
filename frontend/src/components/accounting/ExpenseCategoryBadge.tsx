import { Archive, BriefcaseBusiness, Building2, FileText, Landmark, Package, Store, Truck, Users, Zap } from 'lucide-react';
import './expensePresentation.css';

interface ExpenseCategoryBadgeProps {
  label: string;
  subcategory?: string;
}

export default function ExpenseCategoryBadge({ label, subcategory = '' }: ExpenseCategoryBadgeProps) {
  const styles = [
    { match: /^(transport)/, words: /交通|物流|运输/, tone: 'logistics', Icon: Truck },
    { match: /^personnel/, words: /人员|工资|薪酬/, tone: 'salary', Icon: Users },
    { match: /^(rent|property|venue|facility)/, words: /房租|物业|场地|设备|仓储/, tone: 'facility', Icon: Building2 },
    { match: /^(electricity|water|gas_heating|other_energy)/, words: /水电|能源/, tone: 'facility', Icon: Zap },
    { match: /^marketing/, words: /销售|营销|平台|佣金/, tone: 'platform', Icon: Store },
    { match: /^office/, words: /办公|通讯|行政/, tone: 'office', Icon: BriefcaseBusiness },
    { match: /^professional/, words: /专业|法律|咨询/, tone: 'professional', Icon: FileText },
    { match: /^financial/, words: /财务|利息|银行/, tone: 'financial', Icon: Landmark },
    { match: /^(tax|registration|license|notary)/, words: /税费|政府/, tone: 'financial', Icon: Landmark },
    { match: /^purchase/, words: /采购|进货/, tone: 'purchase', Icon: Package },
  ];
  const style = styles.find(item => item.match.test(subcategory))
    ?? styles.find(item => item.words.test(label));
  const Icon = style?.Icon ?? Archive;
  return <span className={`expense-category expense-category--${style?.tone ?? 'other'}`}>
    <Icon aria-hidden="true" size={12} strokeWidth={1.8} />{label}
  </span>;
}
