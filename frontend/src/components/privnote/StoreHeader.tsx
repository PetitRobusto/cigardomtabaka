import { MapPin, Phone, MessageCircle } from "lucide-react";
import { brandLogoUrl, habanosSpecialistLogoUrl } from "../../utils/brandAssets";

export default function StoreHeader({ compact = false }: { compact?: boolean }) {
  return (
    <div className="bg-accent-light border border-accent/20 rounded-sm px-5 py-5 mb-6 text-center">
      <div className="mb-3 flex items-center justify-center gap-3">
        <img
          src={brandLogoUrl}
          alt="CigarDomTabaka"
          width="120"
          height="120"
          className={`${compact ? "h-12 w-12" : "h-24 w-24 sm:h-[120px] sm:w-[120px]"} object-contain`}
        />
        <span className="h-10 w-px bg-border" aria-hidden="true" />
        <img
          src={habanosSpecialistLogoUrl}
          alt="Habanos Specialist"
          width="173"
          height="216"
          className={`${compact ? "h-12 w-auto" : "h-[72px] w-auto sm:h-20"} object-contain`}
        />
      </div>
      <h2 className="text-lg font-bold tracking-wide text-fg mb-2">
        莫斯科烟草之家
        <br />
        <span className="font-normal text-sm text-muted">
          Москва Сигар дом табака
        </span>
      </h2>
      <div className="mb-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-accent">
        Habanos Specialist · 专业门店资质
      </div>
      {!compact && (
        <p className="mx-auto mb-3 max-w-xl text-xs leading-5 text-muted">
          莫斯科持证雪茄服务商
        </p>
      )}
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
