import { MapPin, Phone, MessageCircle } from "lucide-react";
const base = import.meta.env.BASE_URL;
export default function StoreHeader({ compact = false }: { compact?: boolean }) {
  return (
    <div className="bg-accent-light border border-accent/20 rounded-sm px-5 py-5 mb-6 text-center">
      <img
        src={`${base}logo-512.png`}
        alt="CigarDomTabaka"
        className={`${compact ? "h-12 w-12" : "h-[120px] w-[120px]"} mx-auto mb-3 object-contain`}
      />
      <h2 className="text-lg font-bold tracking-wide text-fg mb-2">
        莫斯科烟草之家
        <br />
        <span className="font-normal text-sm text-muted">
          Москва Сигар дом табака
        </span>
      </h2>
      <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted justify-center">
        <span className="flex items-center gap-1">
          <MapPin className="w-3.5 h-3.5 text-accent" />
          Москва, Молодёжная ул. 3
        </span>
        <span className="flex items-center gap-1">
          <Phone className="w-3.5 h-3.5 text-accent" />
          +7 929 638-48-78
        </span>
        <span className="flex items-center gap-1">
          <MessageCircle className="w-3.5 h-3.5 text-accent" />
          WeChat: cigardomtabaka
        </span>
      </div>
    </div>
  );
}
