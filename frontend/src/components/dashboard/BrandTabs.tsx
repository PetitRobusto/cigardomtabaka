interface BrandTabsProps {
  brands: string[];
  activeBrand: string;
  onSelect: (brand: string) => void;
}

export function BrandTabs({ brands, activeBrand, onSelect }: BrandTabsProps) {
  return (
    <div className="flex flex-wrap gap-2 mb-6 p-2 bg-white rounded-lg shadow-sm border border-stone-100">
      <button
        className={`px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
          !activeBrand
            ? 'bg-gold-500 text-white border border-gold-500 shadow-sm'
            : 'bg-transparent text-stone-700 border border-transparent hover:text-gold-500 hover:bg-stone-100'
        }`}
        onClick={() => onSelect('')}
      >
        全部品牌
      </button>
      {brands.map((b) => (
        <button
          key={b}
          className={`px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
            activeBrand === b
              ? 'bg-gold-500 text-white border border-gold-500 shadow-sm'
              : 'bg-transparent text-stone-700 border border-transparent hover:text-gold-500 hover:bg-stone-100'
          }`}
          onClick={() => onSelect(b)}
        >
          {b}
        </button>
      ))}
    </div>
  );
}
