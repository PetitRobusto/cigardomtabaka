import type { BrandInfo } from '../../types';

interface BrandTabsProps {
  brands: BrandInfo[];
  activeBrand: string;
  onSelect: (brand: string) => void;
}

export function BrandTabs({ brands, activeBrand, onSelect }: BrandTabsProps) {
  return (
    <div className="flex flex-wrap gap-2 mb-6 p-2 bg-white rounded-sm border border-[#E5E5E5]">
      <button
        className={`px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
          !activeBrand
            ? 'bg-[#A16207] text-white border border-[#A16207]'
            : 'bg-transparent text-[#78716C] border border-transparent hover:text-[#A16207] hover:bg-[#F5F5F4]'
        }`}
        onClick={() => onSelect('')}
      >
        全部品牌
      </button>
      {brands.map((b) => (
        <button
          key={b.name}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-all duration-200 ${
            activeBrand === b.name
              ? 'bg-[#A16207] text-white border border-[#A16207]'
              : 'bg-transparent text-[#78716C] border border-transparent hover:text-[#A16207] hover:bg-[#F5F5F4]'
          }`}
          onClick={() => onSelect(b.name)}
        >
          {b.logoUrl && (
            <img
              src={b.logoUrl}
              alt={b.name}
              className="w-6 h-6 object-contain rounded-sm"
              loading="lazy"
            />
          )}
          <span>{b.name}</span>
        </button>
      ))}
    </div>
  );
}
