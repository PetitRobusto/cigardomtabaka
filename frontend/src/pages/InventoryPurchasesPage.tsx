import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Ban,
  ChevronLeft,
  CircleDollarSign,
  Lock,
  MoreHorizontal,
  PackageCheck,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Truck,
  Undo2,
  X,
} from 'lucide-react';
import {
  apiErrorMessage,
  cancelPurchaseOrder,
  createPurchaseOrder,
  fetchAccountingAccounts,
  fetchInventoryPurchase,
  fetchInventoryPurchases,
  payPurchaseOrder,
  receivePurchaseOrder,
  reverseReceivedPurchaseOrder,
  updatePurchaseOrder,
} from '../api';
import { CigarAutocomplete, SupplierAutocomplete } from '../components/search';
import InventorySectionNav from '../components/inventory/InventorySectionNav';
import { usePageMeta } from '../hooks/usePageMeta';
import type {
  FundAccount,
  InventoryPurchaseDirectory,
  PurchaseAction,
  PurchaseActionItem,
  PurchaseSupplier,
  SearchCigarResult,
} from '../types';
import { moscowBusinessDate } from '../utils/businessDate';
import { cigarSearchDisplayName } from '../utils/cigarSearchDisplay';
import {
  PURCHASE_STATUS_FILTERS,
  buildPurchaseDraftPayload,
  purchaseActionMenu,
  purchaseStatusLabel,
  selectPurchaseRubAccountId,
} from './inventoryPurchases.logic';

interface DraftItem {
  cigarId: number;
  cigarName: string;
  cigarEnglishName: string;
  brandCn: string;
  brand: string;
  releaseTypeCn: string;
  isRegular: boolean;
  packagingSizes: number[];
  boxSize: string;
  boxQuantity: string;
  unitPriceRubPerBox: string;
  purchaseUnit?: 'box' | 'stick';
  quantitySticks?: string;
  unitPriceRubPerStick?: string;
}

interface DraftForm {
  id: number | null;
  version: number | null;
  supplier: PurchaseSupplier | null;
  businessDate: string;
  note: string;
  items: DraftItem[];
}

type ModalState =
  | { kind: 'editor'; draft: DraftForm }
  | { kind: 'pay'; purchase: PurchaseAction; accountId: string; businessDate: string }
  | { kind: 'receive'; purchase: PurchaseAction; businessDate: string; note: string }
  | { kind: 'cancel'; purchase: PurchaseAction; note: string }
  | { kind: 'reverse'; purchase: PurchaseAction; businessDate: string; note: string }
  | { kind: 'reverse-confirm'; purchase: PurchaseAction; businessDate: string; note: string };

const today = () => moscowBusinessDate();

function emptyDraft(): DraftForm {
  return {
    id: null,
    version: null,
    supplier: null,
    businessDate: today(),
    note: '',
    items: [],
  };
}

function isWholeNumber(value: string): boolean {
  return /^(?:[1-9]\d*)$/.test(value.trim());
}

function isMoney(value: string): boolean {
  return /^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(value.trim());
}

function displayRub(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '待补';
  const number = Number(value);
  if (!Number.isFinite(number)) return '待补';
  return `₽ ${number.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function displayCny(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return `¥ ${number.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function statusClass(status: string): string {
  return ({
    draft: 'bg-[#F1EDE6] text-[#665C50]',
    in_transit: 'bg-[#EAF0F4] text-[#466681]',
    received: 'bg-[#E9F1EB] text-success',
    cancelled: 'bg-[#F1EDE6] text-[#665C50] line-through',
  })[status] || 'bg-cream text-muted';
}

function itemBoxes(items: PurchaseAction['items']): number {
  return items.reduce((sum, item) => sum + (item.box_quantity || 0), 0);
}

function itemSticks(items: PurchaseAction['items']): number {
  return items.reduce((sum, item) => sum + (item.quantity || 0), 0);
}

function itemSubtotal(item: PurchaseActionItem): string | null {
  const quantity = item.purchase_unit === 'stick' ? (item.quantity_sticks ?? item.quantity) : item.box_quantity;
  const price = item.purchase_unit === 'stick' ? item.unit_price_rub_per_stick : item.unit_price_rub_per_box;
  if (quantity == null || price == null) return null;
  const total = Number(quantity) * Number(price);
  return Number.isFinite(total) ? total.toFixed(2) : null;
}

function draftTotal(items: DraftItem[]): string {
  const total = items.reduce<number | null>((sum, item) => {
    if (sum === null) return null;
    if (item.purchaseUnit === 'stick') {
      if (!isWholeNumber(item.quantitySticks || '') || !isMoney(item.unitPriceRubPerStick || '')) return null;
      return sum + Number(item.quantitySticks || 0) * Number(item.unitPriceRubPerStick || 0);
    }
    if (!isWholeNumber(item.boxQuantity) || !isMoney(item.unitPriceRubPerBox)) return null;
    return sum + Number(item.boxQuantity) * Number(item.unitPriceRubPerBox);
  }, 0);
  return total === null ? '含待补' : displayRub(total);
}

function purchaseToDraft(purchase: PurchaseAction): DraftForm {
  return {
    id: purchase.id,
    version: purchase.version,
    supplier: purchase.supplier_id && purchase.supplier_name ? {
      id: purchase.supplier_id,
      name: purchase.supplier_name,
      phone: purchase.supplier_phone || '',
    } : null,
    businessDate: purchase.business_date || '',
    note: purchase.note || '',
    items: purchase.items.map(item => ({
      cigarId: item.cigar_id,
      cigarName: item.cigar_name || item.cigar_english_name || `雪茄 #${item.cigar_id}`,
      cigarEnglishName: item.cigar_english_name || '',
      brandCn: item.brand_cn || '',
      brand: item.brand || '',
      releaseTypeCn: item.release_type_cn || '',
      isRegular: Boolean(item.is_regular),
      packagingSizes: item.packaging_sizes?.filter(size => size > 0) || [],
      boxSize: item.box_size == null ? '' : String(item.box_size),
      boxQuantity: item.box_quantity == null ? '' : String(item.box_quantity),
      unitPriceRubPerBox: item.unit_price_rub_per_box == null ? '' : String(item.unit_price_rub_per_box),
      purchaseUnit: item.purchase_unit === 'stick' ? 'stick' : 'box',
      quantitySticks: item.quantity == null ? '' : String(item.quantity),
      unitPriceRubPerStick: item.unit_price_rub_per_stick == null ? '' : String(item.unit_price_rub_per_stick),
    })),
  };
}

function cigarToDraftItem(cigar: SearchCigarResult): DraftItem {
  const packagingSizes = cigar.packaging_sizes.filter(size => size > 0);
  return {
    cigarId: cigar.id,
    cigarName: cigar.name || cigar.english_name,
    cigarEnglishName: cigar.english_name,
    brandCn: cigar.brand_cn,
    brand: cigar.brand,
    releaseTypeCn: cigar.release_type_cn,
    isRegular: cigar.is_regular,
    packagingSizes,
    boxSize: packagingSizes.length === 1 ? String(packagingSizes[0]) : '',
    boxQuantity: '',
    unitPriceRubPerBox: '',
    purchaseUnit: 'box',
    quantitySticks: '',
    unitPriceRubPerStick: '',
  };
}

function toPayloadItems(items: DraftItem[]): PurchaseActionItem[] {
  return items.map(item => item.purchaseUnit === 'stick' ? ({
    cigar_id: item.cigarId,
    purchase_unit: 'stick',
    box_size: null,
    box_quantity: null,
    quantity_sticks: isWholeNumber(item.quantitySticks || '') ? Number(item.quantitySticks || 0) : null,
    unit_price_rub_per_box: null,
    unit_price_rub_per_stick: isMoney(item.unitPriceRubPerStick || '') ? (item.unitPriceRubPerStick || '').trim() : null,
  }) : ({
    cigar_id: item.cigarId,
    purchase_unit: 'box',
    box_size: isWholeNumber(item.boxSize) ? Number(item.boxSize) : null,
    box_quantity: isWholeNumber(item.boxQuantity) ? Number(item.boxQuantity) : null,
    unit_price_rub_per_box: isMoney(item.unitPriceRubPerBox) ? item.unitPriceRubPerBox.trim() : null,
    unit_price_rub_per_stick: null,
  }));
}

export default function InventoryPurchasesPage() {
  const { setMeta } = usePageMeta();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [saving, setSaving] = useState(false);
  const [modalError, setModalError] = useState('');
  const [toast, setToast] = useState('');
  const [moreOpen, setMoreOpen] = useState(false);

  useEffect(() => {
    setMeta({ title: '采购单', breadcrumbs: [{ label: '首页', to: '/' }, { label: '现货库存', to: '/inventory' }, { label: '采购单' }] });
  }, [setMeta]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(''), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const directoryQuery = useQuery({
    queryKey: ['inventory-purchases', search, status, dateFrom, dateTo],
    queryFn: () => fetchInventoryPurchases({
      q: search.trim() || undefined,
      status: status || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      limit: 100,
    }),
  });
  const accountsQuery = useQuery({ queryKey: ['accounting-accounts'], queryFn: fetchAccountingAccounts });
  const detailQuery = useQuery({
    queryKey: ['inventory-purchase', selectedId],
    queryFn: () => fetchInventoryPurchase(selectedId as number),
    enabled: selectedId !== null,
  });

  const purchases = directoryQuery.data?.results || [];
  const selectedFromDirectory = purchases.find(purchase => purchase.id === selectedId) || null;
  // 筛选后若当前单据已不在目录，详情也应随列表一起隐藏，避免展示筛选范围外的旧快照。
  const selected = selectedFromDirectory ? (detailQuery.data || selectedFromDirectory) : null;
  const accounts = accountsQuery.data || [];
  const activeRubAccounts = accounts.filter(account => account.currency === 'RUB' && account.is_active);

  const invalidatePurchases = () => {
    queryClient.invalidateQueries({ queryKey: ['inventory-purchases'] });
    queryClient.invalidateQueries({ queryKey: ['inventory-purchase'] });
    queryClient.invalidateQueries({ queryKey: ['inventory'] });
    queryClient.invalidateQueries({ queryKey: ['accounting-dashboard'] });
    queryClient.invalidateQueries({ queryKey: ['accounting-accounts'] });
    queryClient.invalidateQueries({ queryKey: ['accounting-summary'] });
    queryClient.invalidateQueries({ queryKey: ['monthly-profit'] });
    queryClient.invalidateQueries({ queryKey: ['accounting-actions'] });
  };

  const openModal = (next: ModalState) => {
    setModalError('');
    setMoreOpen(false);
    setModal(next);
  };

  const saveDraft = async (draft: DraftForm) => {
    setSaving(true);
    setModalError('');
    const payload = buildPurchaseDraftPayload({
      supplier_id: draft.supplier?.id || null,
      business_date: draft.businessDate || null,
      items: toPayloadItems(draft.items),
      note: draft.note,
    });
    try {
      const result = draft.id === null
        ? await createPurchaseOrder(payload)
        : await updatePurchaseOrder(draft.id, { ...payload, expected_version: draft.version as number });
      invalidatePurchases();
      setSelectedId(result.id);
      setModal(null);
      setToast(draft.id === null ? '采购草稿已保存' : '采购草稿已更新');
    } catch (error) {
      setModalError(apiErrorMessage(error, '采购草稿保存失败'));
    } finally {
      setSaving(false);
    }
  };

  const pay = async (purchase: PurchaseAction, accountId: string, businessDate: string) => {
    if (!accountId || !businessDate) return;
    setSaving(true);
    setModalError('');
    try {
      await payPurchaseOrder(purchase.id, { rub_account_id: Number(accountId), business_date: businessDate });
      invalidatePurchases();
      setModal(null);
      setToast(`${purchase.order_number || `采购单 #${purchase.id}`} 已整单付款`);
    } catch (error) {
      setModalError(apiErrorMessage(error, '采购付款失败'));
    } finally {
      setSaving(false);
    }
  };

  const receive = async (purchase: PurchaseAction, businessDate: string, note: string) => {
    if (!businessDate) return;
    setSaving(true);
    setModalError('');
    try {
      const batches = await receivePurchaseOrder(purchase.id, { business_date: businessDate, note });
      invalidatePurchases();
      setModal(null);
      setToast(`整单到货完成，已生成 ${batches.length} 条库存批次`);
    } catch (error) {
      setModalError(apiErrorMessage(error, '整单到货失败'));
    } finally {
      setSaving(false);
    }
  };

  const cancel = async (purchase: PurchaseAction, note: string) => {
    setSaving(true);
    setModalError('');
    try {
      await cancelPurchaseOrder(purchase.id, { expected_version: purchase.version, note });
      invalidatePurchases();
      setModal(null);
      setToast('采购草稿已取消');
    } catch (error) {
      setModalError(apiErrorMessage(error, '取消采购草稿失败'));
    } finally {
      setSaving(false);
    }
  };

  const reverseReceipt = async (purchase: PurchaseAction, businessDate: string, note: string) => {
    if (!businessDate || !note.trim()) return;
    setSaving(true);
    setModalError('');
    try {
      await reverseReceivedPurchaseOrder(purchase.id, { business_date: businessDate, note: note.trim() });
      invalidatePurchases();
      setModal(null);
      setToast('到货已撤回，采购单回到待到货状态');
    } catch (error) {
      setModalError(apiErrorMessage(error, '撤回到货失败；若批次已经出库，需先处理后续库存动作'));
    } finally {
      setSaving(false);
    }
  };

  const resetFilters = () => {
    setSearch('');
    setStatus('');
    setDateFrom('');
    setDateTo('');
  };

  return <div className="w-full animate-fade-in">
    <InventorySectionNav />
    <header className="mb-5 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Inventory / Purchases</p>
        <h1 className="mt-1 font-display text-3xl font-semibold sm:text-4xl">采购单</h1>
        <p className="mt-2 text-sm text-muted">整单付款、整单到货：草稿可补全，付款即锁定，到货生成库存批次。</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => invalidatePurchases()} className="inline-flex items-center gap-1 rounded border border-border bg-white px-3 py-2 text-sm hover:border-gold"><RefreshCw className="h-4 w-4" />刷新</button>
        <button type="button" onClick={() => openModal({ kind: 'editor', draft: emptyDraft() })} className="inline-flex items-center gap-1 rounded bg-accent px-3 py-2 text-sm font-semibold text-white hover:bg-accent-hover"><Plus className="h-4 w-4" />新建采购单</button>
      </div>
    </header>

    <PurchaseStats stats={directoryQuery.data?.stats} />

    <section className="mb-4 rounded-md border border-border bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-[11px] font-semibold text-muted">业务日期<input type="date" value={dateFrom} onChange={event => setDateFrom(event.target.value)} className="mt-1 block rounded border border-border px-2 py-1.5 text-xs text-fg" /></label>
        <span className="pb-2 text-xs text-muted">至</span>
        <label className="text-[11px] font-semibold text-muted"><span className="sr-only">结束日期</span><input type="date" value={dateTo} onChange={event => setDateTo(event.target.value)} className="mt-1 block rounded border border-border px-2 py-1.5 text-xs text-fg" /></label>
        <div className="flex flex-wrap gap-1">{PURCHASE_STATUS_FILTERS.map(option => <button key={option.value} type="button" onClick={() => setStatus(option.value)} className={'rounded-full border px-3 py-1.5 text-xs font-semibold ' + (status === option.value ? 'border-fg bg-fg text-white' : 'border-border text-muted hover:border-gold hover:text-fg')}>{option.label}</button>)}</div>
        <div className="relative min-w-52 flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索单号、供应商或商品" className="w-full rounded border border-border py-2 pl-9 pr-3 text-sm outline-none focus:border-gold" /></div>
      </div>
    </section>

    {directoryQuery.error && <p role="alert" className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{apiErrorMessage(directoryQuery.error, '采购单加载失败')}</p>}
    {accountsQuery.error && <p role="alert" className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">卢布账户加载失败，暂不能确认采购付款。</p>}

    {directoryQuery.isLoading ? <div className="rounded-md border border-border bg-white px-5 py-20 text-center text-sm text-muted">加载采购单工作台…</div> : <div className={'grid gap-4 lg:grid-cols-[400px_minmax(0,1fr)] lg:items-start ' + (selected ? 'max-lg:[&_.purchase-list]:hidden' : '')}>
      <section aria-label="采购单列表" className="purchase-list max-h-[calc(100vh-15rem)] overflow-y-auto rounded-md border border-border bg-white shadow-sm lg:sticky lg:top-20">
        {purchases.length ? purchases.map(purchase => <PurchaseListRow key={purchase.id} purchase={purchase} selected={purchase.id === selectedId} onClick={() => setSelectedId(purchase.id)} />) : <EmptyFiltered onReset={resetFilters} />}
      </section>
      <section aria-label="采购单详情" className="min-w-0 rounded-md border border-border bg-white shadow-sm lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto">
        {detailQuery.isLoading && selectedId ? <div className="px-5 py-20 text-center text-sm text-muted">加载采购单详情…</div> : selected ? <PurchaseDetail
          purchase={selected}
          moreOpen={moreOpen}
          onBack={() => setSelectedId(null)}
          onEdit={() => openModal({ kind: 'editor', draft: purchaseToDraft(selected) })}
          onPay={() => openModal({ kind: 'pay', purchase: selected, accountId: String(selectPurchaseRubAccountId(accounts, null) || ''), businessDate: today() })}
          onReceive={() => openModal({ kind: 'receive', purchase: selected, businessDate: today(), note: '' })}
          onCancel={() => openModal({ kind: 'cancel', purchase: selected, note: '' })}
          onToggleMore={() => setMoreOpen(open => !open)}
          onReverse={() => openModal({ kind: 'reverse', purchase: selected, businessDate: today(), note: '' })}
        /> : <EmptySelection />}
      </section>
    </div>}

    {modal && <ModalFrame editor={modal.kind === 'editor'} onClose={() => !saving && setModal(null)}>
      {modal.kind === 'editor' && <DraftEditor
        draft={modal.draft}
        busy={saving}
        error={modalError}
        onChange={draft => setModal({ kind: 'editor', draft })}
        onClose={() => setModal(null)}
        onSave={() => void saveDraft(modal.draft)}
      />}
      {modal.kind === 'pay' && <PayDialog
        purchase={modal.purchase}
        accountId={modal.accountId}
        businessDate={modal.businessDate}
        accounts={activeRubAccounts}
        busy={saving}
        error={modalError}
        onChange={patch => setModal({ ...modal, ...patch })}
        onClose={() => setModal(null)}
        onConfirm={() => void pay(modal.purchase, modal.accountId, modal.businessDate)}
      />}
      {modal.kind === 'receive' && <ReceiveDialog
        purchase={modal.purchase}
        businessDate={modal.businessDate}
        note={modal.note}
        busy={saving}
        error={modalError}
        onChange={patch => setModal({ ...modal, ...patch })}
        onClose={() => setModal(null)}
        onConfirm={() => void receive(modal.purchase, modal.businessDate, modal.note)}
      />}
      {modal.kind === 'cancel' && <CancelDialog
        purchase={modal.purchase}
        note={modal.note}
        busy={saving}
        error={modalError}
        onChange={note => setModal({ ...modal, note })}
        onClose={() => setModal(null)}
        onConfirm={() => void cancel(modal.purchase, modal.note)}
      />}
      {modal.kind === 'reverse' && <ReverseDialog
        purchase={modal.purchase}
        businessDate={modal.businessDate}
        note={modal.note}
        busy={saving}
        error={modalError}
        onChange={patch => setModal({ ...modal, ...patch })}
        onClose={() => setModal(null)}
        onNext={() => {
          if (!modal.businessDate || !modal.note.trim()) {
            setModalError('请填写撤回日期和原因。');
            return;
          }
          setModalError('');
          setModal({ kind: 'reverse-confirm', purchase: modal.purchase, businessDate: modal.businessDate, note: modal.note.trim() });
        }}
      />}
      {modal.kind === 'reverse-confirm' && <ReverseConfirmDialog
        purchase={modal.purchase}
        businessDate={modal.businessDate}
        note={modal.note}
        busy={saving}
        error={modalError}
        onBack={() => { setModalError(''); setModal({ kind: 'reverse', purchase: modal.purchase, businessDate: modal.businessDate, note: modal.note }); }}
        onClose={() => setModal(null)}
        onConfirm={() => void reverseReceipt(modal.purchase, modal.businessDate, modal.note)}
      />}
    </ModalFrame>}
    {toast && <p role="status" className="fixed bottom-6 left-1/2 z-[70] -translate-x-1/2 rounded border border-[#C8DFCE] bg-white px-4 py-2.5 text-sm font-medium text-success shadow-lg">{toast}</p>}
  </div>;
}

function PurchaseStats({ stats }: { stats: InventoryPurchaseDirectory['stats'] | undefined }) {
  const cells = [
    { label: '采购单总数', value: String(stats?.total || 0), hint: `草稿 ${stats?.draft || 0} 单` },
    { label: '待到货 · 已付款', value: displayRub(stats?.in_transit_rub), hint: `${stats?.in_transit || 0} 单在途 · 不支持分批到货`, tone: 'text-[#466681]' },
    { label: '本月到货', value: `${Number(stats?.month_received_sticks || 0).toLocaleString('zh-CN')} 支`, hint: `${stats?.received || 0} 单已到货`, tone: 'text-success' },
    { label: '本月 RUB 付款合计', value: displayRub(stats?.month_paid_rub), hint: '按整单全额 · 一次付清' },
  ];
  return <section className="mb-4 grid grid-cols-2 overflow-hidden rounded-md border border-border bg-white shadow-sm xl:grid-cols-4">{cells.map(cell => <div key={cell.label} className="border-b border-r border-border p-4 last:border-r-0 xl:border-b-0"><p className="text-[11px] uppercase tracking-wider text-muted">{cell.label}</p><strong className={'mt-2 block font-mono text-xl font-semibold ' + (cell.tone || '')}>{cell.value}</strong><small className="mt-1 block text-[10px] text-muted">{cell.hint}</small></div>)}</section>;
}

function PurchaseListRow({ purchase, selected, onClick }: { purchase: PurchaseAction; selected: boolean; onClick: () => void }) {
  return <button type="button" onClick={onClick} className={'block w-full border-b border-border px-4 py-3 text-left last:border-b-0 hover:bg-[#FFFCF8] ' + (selected ? 'border-l-[3px] border-l-accent bg-[#FFFCF4] pl-[13px]' : '')}>
    <div className="flex items-baseline justify-between gap-3"><span className="font-mono text-xs font-semibold text-fg">{purchase.order_number || `PO-${purchase.id}`}</span><strong className="font-mono text-sm">{displayRub(purchase.rub_total)}</strong></div>
    <p className="mt-1 truncate text-sm font-semibold">{purchase.supplier_name || '待补供应商'}</p>
    <div className="mt-2 flex items-center justify-between gap-2"><span className="font-mono text-[10px] text-muted">{purchase.business_date || '日期待补'} · {itemBoxes(purchase.items)} 盒 / {itemSticks(purchase.items)} 支</span><StatusPill status={purchase.status} /></div>
  </button>;
}

function StatusPill({ status }: { status: string }) {
  return <span className={'inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ' + statusClass(status)}><i className="h-1.5 w-1.5 rounded-full bg-current" />{purchaseStatusLabel(status)}</span>;
}

function EmptyFiltered({ onReset }: { onReset: () => void }) {
  return <div className="px-5 py-16 text-center"><Search className="mx-auto h-6 w-6 text-muted" /><p className="mt-3 text-sm font-semibold">未找到匹配采购单</p><p className="mt-1 text-xs text-muted">尝试放宽搜索或筛选条件。</p><button type="button" onClick={onReset} className="mt-4 rounded border border-border bg-white px-3 py-1.5 text-xs font-semibold hover:border-gold">清除筛选</button></div>;
}

function EmptySelection() {
  return <div className="px-5 py-24 text-center"><ChevronLeft className="mx-auto h-6 w-6 rotate-180 text-muted" /><p className="mt-3 text-sm font-semibold">请选择一笔采购单</p><p className="mt-1 text-xs text-muted">从左侧查看商品明细、付款事实和库存批次。</p></div>;
}

function PurchaseDetail({
  purchase,
  moreOpen,
  onBack,
  onEdit,
  onPay,
  onReceive,
  onCancel,
  onToggleMore,
  onReverse,
}: {
  purchase: PurchaseAction;
  moreOpen: boolean;
  onBack: () => void;
  onEdit: () => void;
  onPay: () => void;
  onReceive: () => void;
  onCancel: () => void;
  onToggleMore: () => void;
  onReverse: () => void;
}) {
  const batchCount = purchase.items.reduce((sum, item) => sum + (item.batches?.length || 0), 0);
  const actionMenu = purchaseActionMenu(purchase.status);
  const action = actionMenu.primary.includes('pay') ? <><button type="button" onClick={onPay} className="inline-flex items-center gap-1 rounded bg-accent px-3 py-2 text-xs font-semibold text-white hover:bg-accent-hover"><CircleDollarSign className="h-3.5 w-3.5" />付款 · 整单付清</button><button type="button" onClick={onEdit} className="inline-flex items-center gap-1 rounded border border-border bg-white px-3 py-2 text-xs font-semibold hover:border-gold"><Pencil className="h-3.5 w-3.5" />编辑草稿</button><button type="button" onClick={onCancel} className="inline-flex items-center gap-1 rounded border border-[#E3C3C6] bg-white px-3 py-2 text-xs font-semibold text-accent hover:bg-accent-light"><Ban className="h-3.5 w-3.5" />取消草稿</button></> : actionMenu.primary.includes('receive') ? <><button type="button" onClick={onReceive} className="inline-flex items-center gap-1 rounded bg-accent px-3 py-2 text-xs font-semibold text-white hover:bg-accent-hover"><Truck className="h-3.5 w-3.5" />确认整单到货</button><span className="inline-flex items-center gap-1 text-[11px] text-muted"><Lock className="h-3.5 w-3.5" />付款后字段已锁定</span></> : actionMenu.more.includes('reverse_receive') ? <><span className="inline-flex items-center gap-1 text-[11px] text-muted"><PackageCheck className="h-3.5 w-3.5" />已入库 · 库存批次 {batchCount} 条</span><div className="relative"><button type="button" onClick={onToggleMore} className="inline-flex items-center gap-1 rounded border border-border bg-white px-3 py-2 text-xs font-semibold hover:border-gold"><MoreHorizontal className="h-3.5 w-3.5" />更多操作</button>{moreOpen && <div role="menu" className="absolute right-0 z-20 mt-1 w-52 rounded-md border border-border bg-white p-1 shadow-lg"><p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted">低频 · 危险</p><button type="button" role="menuitem" onClick={onReverse} className="flex w-full items-center justify-between rounded px-2 py-2 text-left text-xs font-semibold text-accent hover:bg-accent-light"><span className="inline-flex items-center gap-1"><Undo2 className="h-3.5 w-3.5" />撤回到货</span><small className="font-normal text-muted">撤销批次</small></button></div>}</div></> : <span className="text-xs text-muted">已取消 · 无可用操作</span>;

  return <>
    <header className="border-b border-border bg-[#FFFDF9] px-4 py-4 sm:px-5">
      <button type="button" onClick={onBack} className="mb-3 inline-flex items-center gap-1 rounded border border-border bg-white px-2.5 py-1.5 text-xs font-semibold text-muted hover:border-gold lg:hidden"><ChevronLeft className="h-3.5 w-3.5" />返回列表</button>
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-display text-xl font-semibold">{purchase.order_number || `采购单 #${purchase.id}`}</h2><p className="mt-1 text-xs text-muted">{purchase.supplier_name ? `${purchase.supplier_name} · ` : ''}业务日期 {purchase.business_date || '待补'} · {purchase.status === 'draft' ? '草稿 · 可稍后补全' : purchase.status === 'in_transit' ? '已付款 · 待到货' : purchase.status === 'received' ? '已到货入库' : '已取消'}</p></div><StatusPill status={purchase.status} /></div>
      <div className="mt-3 flex flex-wrap items-center gap-2">{action}</div>
    </header>
    <DetailInfo purchase={purchase} />
    <DetailItems purchase={purchase} />
    <DetailAmounts purchase={purchase} />
    <DetailFacts purchase={purchase} />
  </>;
}

function DetailInfo({ purchase }: { purchase: PurchaseAction }) {
  const facts = [
    ['供应商', purchase.supplier_name ? `${purchase.supplier_name}${purchase.supplier_phone ? ` · ${purchase.supplier_phone}` : ''}` : '待补'],
    ['业务日期', purchase.business_date || '待补'],
    ['草稿版本', `v${purchase.version}`],
    ['备注', purchase.note || '—'],
  ];
  return <section className="border-b border-border px-4 py-4 sm:px-5"><h3 className="text-xs font-bold tracking-wide">基本信息</h3><dl className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2">{facts.map(([label, value]) => <div key={label}><dt className="text-[10px] text-muted">{label}</dt><dd className="mt-1 text-sm font-medium">{value}</dd></div>)}</dl></section>;
}

export function DetailItems({ purchase }: { purchase: PurchaseAction }) {
  const sticks = itemSticks(purchase.items);
  return <section className="border-b border-border px-4 py-4 sm:px-5"><div className="flex items-center justify-between gap-3"><h3 className="text-xs font-bold tracking-wide">商品明细</h3><span className="font-mono text-[10px] text-muted">{purchase.items.length} 个 SKU · {itemBoxes(purchase.items)} 盒 / {sticks} 支</span></div>{purchase.items.length ? <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[650px] border-collapse text-xs"><thead><tr className="border-b border-border text-left text-[10px] text-muted"><th className="px-2 py-2 font-semibold">商品</th><th className="px-2 py-2 font-semibold">采购单位</th><th className="px-2 py-2 font-semibold">数量</th><th className="px-2 py-2 text-right font-semibold">单价 RUB</th><th className="px-2 py-2 text-right font-semibold">小计</th></tr></thead><tbody>{purchase.items.map((item, index) => { const stickMode = item.purchase_unit === 'stick'; return <tr key={item.id || `${item.cigar_id}-${index}`} className="border-b border-[#F3EFE8] last:border-b-0"><td className="px-2 py-2.5"><p className="font-semibold">{cigarSearchDisplayName({ name: item.cigar_name || item.cigar_english_name || `雪茄 #${item.cigar_id}`, brand: item.brand || '', brand_cn: item.brand_cn || '' })} <ReleasePill item={item} /></p>{item.cigar_english_name && <small className="block pt-0.5 text-[10px] text-muted">{item.cigar_english_name}</small>}{item.batches?.map(batch => <div key={batch.id} className="mt-1 flex justify-between gap-3 border-t border-dashed border-border pt-1 text-[10px] text-muted"><span>库存批次 #{batch.id}</span><span className="font-mono text-fg">{batch.quantity} 支入库</span></div>)}</td><td className="px-2 py-2.5">{stickMode ? '按支' : '按盒'}</td><td className="px-2 py-2.5">{stickMode ? `${item.quantity_sticks ?? item.quantity ?? '待补'} 支` : item.box_quantity == null ? '待补' : `${item.box_quantity} 盒（${item.box_size || '?'} 支/盒）`}</td><td className="px-2 py-2.5 text-right font-mono">{displayRub(stickMode ? item.unit_price_rub_per_stick : item.unit_price_rub_per_box)}</td><td className="px-2 py-2.5 text-right font-mono font-semibold">{displayRub(itemSubtotal(item))}</td></tr>; })}</tbody></table></div> : <p className="mt-3 rounded border border-dashed border-border px-3 py-4 text-center text-xs text-muted">草稿还没有商品，可稍后补全。</p>}</section>;
}

function ReleasePill({ item }: { item: PurchaseActionItem }) {
  const label = item.is_regular ? '常规款' : item.release_type_cn || '特别款';
  return <span className={'ml-1 inline-flex rounded-full px-1.5 py-0.5 align-middle text-[9px] font-bold ' + (item.is_regular ? 'border border-border bg-white text-muted' : 'bg-[#F5E8D8] text-gold')}>{label}</span>;
}

function DetailAmounts({ purchase }: { purchase: PurchaseAction }) {
  return <section className="border-b border-border px-4 py-4 sm:px-5"><div className="flex items-center justify-between"><h3 className="text-xs font-bold tracking-wide">金额</h3><span className="font-mono text-[10px] text-muted">RUB 结算</span></div><div className="mt-3 space-y-2 text-sm"><div className="flex justify-between gap-4 border-t border-border pt-3"><span>采购单 RUB 总额{purchase.status === 'draft' && !purchase.draft_complete ? <small className="ml-1 text-[10px] text-[#A75B27]">含待补</small> : null}</span><strong className="font-mono text-base">{displayRub(purchase.rub_total)}</strong></div><div className="flex justify-between gap-4 text-muted"><span>人民币实际成本</span><strong className="font-mono text-fg">{purchase.paid_cny_cost && Number(purchase.paid_cny_cost) > 0 ? displayCny(purchase.paid_cny_cost) : '待付款后确认'}</strong></div></div></section>;
}

function DetailFacts({ purchase }: { purchase: PurchaseAction }) {
  const batches = purchase.items.flatMap(item => item.batches || []);
  return <section className="px-4 py-4 sm:px-5"><div className="flex items-center justify-between"><h3 className="text-xs font-bold tracking-wide">单据事实</h3><span className="font-mono text-[10px] text-muted">{Number(Boolean(purchase.paid_at)) + Number(Boolean(purchase.received_at))} 张</span></div>{purchase.paid_at || purchase.received_at ? <div className="mt-3 grid gap-2 md:grid-cols-2">{purchase.paid_at && <article className="border-l-[3px] border-l-success rounded border border-border bg-[#FFFDF9] p-3"><p className="text-[10px] font-bold uppercase tracking-wider text-muted">PurchasePayment · 付款事实</p><strong className="mt-2 block font-mono text-base">{displayRub(purchase.rub_total)}</strong><p className="mt-1 text-[11px] text-muted">一次性付清 · 人民币成本 {displayCny(purchase.paid_cny_cost)}<br />{formatDateTime(purchase.paid_at)}</p></article>}{purchase.received_at && <article className="border-l-[3px] border-l-[#466681] rounded border border-border bg-[#FFFDF9] p-3"><p className="text-[10px] font-bold uppercase tracking-wider text-muted">GoodsReceipt · 到货事实</p><strong className="mt-2 block font-mono text-base">{itemSticks(purchase.items)} 支入库</strong><p className="mt-1 text-[11px] text-muted">库存批次 {batches.length} 条<br />{formatDateTime(purchase.received_at)}</p></article>}</div> : <p className="mt-3 rounded border border-dashed border-border px-3 py-4 text-center text-xs text-muted">暂无单据 · 付款和到货动作会生成对应事实。</p>}</section>;
}

function formatDateTime(value: string): string {
  if (!value.includes('T')) return value;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Europe/Moscow', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date).replace(/\//g, '-');
}

export function ModalFrame({ children, onClose, editor = false }: { children: React.ReactNode; onClose: () => void; editor?: boolean }) {
  return <div role="presentation" className={'fixed inset-0 z-50 flex justify-center bg-fg/40 backdrop-blur-sm ' + (editor ? 'items-stretch p-0 sm:items-center sm:p-[3dvh]' : 'items-center p-3')} onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}><div role="dialog" aria-modal="true" className={editor ? 'flex h-dvh max-h-dvh w-full max-w-6xl flex-col overflow-hidden bg-white shadow-2xl sm:h-[94dvh] sm:max-h-[94dvh] sm:rounded-lg' : 'max-h-[calc(100dvh-1.5rem)] w-full max-w-lg overflow-y-auto rounded-lg bg-white shadow-2xl'}>{children}</div></div>;
}

function DialogHeader({ title, subtitle, onClose }: { title: string; subtitle: string; onClose: () => void }) {
  return <header className="flex shrink-0 items-start justify-between gap-4 border-b border-border px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:px-6 sm:py-4"><div><h2 className="font-display text-lg font-semibold sm:text-xl">{title}</h2><p className="mt-1 text-[11px] text-muted sm:text-xs">{subtitle}</p></div><button type="button" onClick={onClose} aria-label="关闭" className="grid h-9 w-9 shrink-0 place-items-center rounded border border-border text-muted hover:border-gold hover:text-fg sm:h-8 sm:w-8"><X className="h-4 w-4" /></button></header>;
}

function ModalError({ error }: { error: string }) {
  return error ? <p role="alert" className="mt-3 rounded border border-[#E3C3C6] bg-[#FAF1F0] px-3 py-2 text-xs leading-5 text-accent">{error}</p> : null;
}

export function DraftEditor({ draft, busy, error, onChange, onClose, onSave }: { draft: DraftForm; busy: boolean; error: string; onChange: (draft: DraftForm) => void; onClose: () => void; onSave: () => void }) {
  const patch = (value: Partial<DraftForm>) => onChange({ ...draft, ...value });
  const patchItem = (index: number, value: Partial<DraftItem>) => onChange({ ...draft, items: draft.items.map((item, itemIndex) => itemIndex === index ? { ...item, ...value } : item) });
  const addCigar = (cigar: SearchCigarResult) => {
    if (draft.items.some(item => item.cigarId === cigar.id)) return false;
    patch({ items: [...draft.items, cigarToDraftItem(cigar)] });
    return true;
  };
  const isComplete = Boolean(draft.supplier && draft.businessDate && draft.items.length && draft.items.every(item => item.purchaseUnit === 'stick' ? isWholeNumber(item.quantitySticks || '') && isMoney(item.unitPriceRubPerStick || '') : isWholeNumber(item.boxSize) && isWholeNumber(item.boxQuantity) && isMoney(item.unitPriceRubPerBox)));
  return <div className="flex min-h-0 w-full flex-1 flex-col">
    <DialogHeader title={draft.id === null ? '新建采购单' : `编辑 ${draft.id ? `采购单 #${draft.id}` : '采购草稿'}`} subtitle="保存后为草稿：供应商、日期、商品、盒数与价格均可稍后补全；付款时才严格校验。" onClose={onClose} />
    <div data-purchase-modal-body="scroll" className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6 sm:py-5"><div className="grid gap-4 md:grid-cols-2"><SupplierAutocomplete value={draft.supplier} onChange={supplier => patch({ supplier })} disabled={busy} /><label className="text-[11px] font-semibold tracking-wide text-muted">业务日期<input type="date" disabled={busy} value={draft.businessDate} onChange={event => patch({ businessDate: event.target.value })} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold disabled:bg-cream" /></label></div><label className="mt-4 block text-[11px] font-semibold tracking-wide text-muted">备注<textarea disabled={busy} value={draft.note} onChange={event => patch({ note: event.target.value })} placeholder="例如：等待供应商确认配额与最终报价" rows={2} className="mt-1.5 w-full resize-y rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold disabled:bg-cream" /></label>
      <div className="mt-5 border-t border-border pt-4"><div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="text-sm font-semibold">商品明细</h3><p className="mt-1 text-[11px] text-muted">从目录搜索添加商品；品牌英文名与常规款标记已同步展示。</p></div><span className="rounded bg-[#F5E8D8] px-2 py-1 font-mono text-xs font-semibold text-gold">RUB 总额 {draftTotal(draft.items)}</span></div>
        <div className="mt-4 max-w-xl"><CigarAutocomplete onSelect={addCigar} stockOnly={false} label="添加商品" placeholder="输入英文品牌、中文名或英文名" disabled={busy} resultDetail={cigar => { const sizes = (cigar as SearchCigarResult & { packaging_sizes?: number[] }).packaging_sizes || []; return sizes.length ? `可用盒规 ${sizes.join(' / ')} 支` : '盒规可稍后补全'; }} /></div>
        {draft.items.length ? <div className="mt-4 divide-y divide-border border-y border-border">{draft.items.map((item, index) => <DraftItemRow key={item.cigarId} item={item} busy={busy} onChange={value => patchItem(index, value)} onRemove={() => patch({ items: draft.items.filter((_, itemIndex) => itemIndex !== index) })} />)}</div> : <p className="mt-4 rounded border border-dashed border-border px-3 py-5 text-center text-xs text-muted">草稿可以先不添加商品；需要付款时再补全即可。</p>}
      </div><ModalError error={error} /></div>
    <footer className="flex shrink-0 flex-col items-stretch gap-2 border-t border-border bg-[#FFFDF9] px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 sm:flex-row sm:items-center sm:justify-between sm:gap-3 sm:px-6 sm:py-4"><p className="text-[11px] text-muted">{isComplete ? '付款所需字段已完整；付款后供应商、商品、数量和价格将锁定。' : '草稿允许不完整保存，尚未填写的字段不会阻止保存。'}</p><div className="grid grid-cols-[1fr_1.6fr] gap-2 sm:flex"><button type="button" disabled={busy} onClick={onClose} className="min-h-11 rounded border border-border bg-white px-3 py-2 text-sm font-semibold hover:border-gold disabled:opacity-50 sm:min-h-0">取消</button><button type="button" disabled={busy} onClick={onSave} className="min-h-11 rounded bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-hover disabled:opacity-50 sm:min-h-0">{busy ? '保存中…' : '保存草稿'}</button></div></footer>
  </div>;
}

function DraftItemRow({ item, busy, onChange, onRemove }: { item: DraftItem; busy: boolean; onChange: (patch: Partial<DraftItem>) => void; onRemove: () => void }) {
  const name = cigarSearchDisplayName({
    name: item.cigarName || item.cigarEnglishName || `雪茄 #${item.cigarId}`,
    brand: item.brand,
    brand_cn: item.brandCn,
  });
  const currentBoxSize = Number(item.boxSize);
  const boxSizeOptions = Array.from(new Set([
    ...item.packagingSizes.filter(size => Number.isInteger(size) && size > 0),
    ...(Number.isInteger(currentBoxSize) && currentBoxSize > 0 ? [currentBoxSize] : []),
  ])).sort((left, right) => left - right);
  const stickMode = item.purchaseUnit === 'stick';
  const subtotal = stickMode
    ? isWholeNumber(item.quantitySticks || '') && isMoney(item.unitPriceRubPerStick || '')
      ? displayRub(Number(item.quantitySticks || 0) * Number(item.unitPriceRubPerStick || 0))
      : '待补'
    : isWholeNumber(item.boxQuantity) && isMoney(item.unitPriceRubPerBox)
      ? displayRub(Number(item.boxQuantity) * Number(item.unitPriceRubPerBox))
      : '待补';
  return <article className="grid gap-3 py-4 md:grid-cols-[minmax(220px,1.7fr)_110px_90px_90px_120px_108px_32px] md:items-end">
    <div><p className="text-sm font-semibold">{name} <span className={'ml-1 inline-flex rounded-full px-1.5 py-0.5 text-[9px] font-bold ' + (item.isRegular ? 'border border-border bg-white text-muted' : 'bg-[#F5E8D8] text-gold')}>{item.isRegular ? '常规款' : item.releaseTypeCn || '特别款'}</span></p><p className="mt-1 text-[11px] text-muted">{item.cigarEnglishName}{item.packagingSizes.length ? ` · 目录盒规 ${item.packagingSizes.join(' / ')} 支` : ''}</p></div>
    <label className="text-[10px] font-semibold text-muted">采购单位<select disabled={busy} value={item.purchaseUnit} onChange={event => onChange({ purchaseUnit: event.target.value === 'stick' ? 'stick' : 'box' })} className="mt-1 block w-full rounded border border-border bg-white px-2 py-2 text-sm outline-none focus:border-gold disabled:bg-cream"><option value="box">按盒</option><option value="stick">非常用：按支</option></select></label>
    {stickMode ? <><label className="text-[10px] font-semibold text-muted">支数<input disabled={busy} value={item.quantitySticks || ''} onChange={event => onChange({ quantitySticks: event.target.value })} inputMode="numeric" placeholder="待补" className="mt-1 block w-full rounded border border-border px-2 py-2 text-right text-sm outline-none focus:border-gold disabled:bg-cream" /></label><label className="text-[10px] font-semibold text-muted">每支 RUB<input disabled={busy} value={item.unitPriceRubPerStick || ''} onChange={event => onChange({ unitPriceRubPerStick: event.target.value })} inputMode="decimal" placeholder="待补" className="mt-1 block w-full rounded border border-border px-2 py-2 text-right text-sm outline-none focus:border-gold disabled:bg-cream" /></label><div className="text-[10px] text-muted">到货后进入散支库存</div></> : <><label className="text-[10px] font-semibold text-muted">盒规{boxSizeOptions.length ? <select disabled={busy} value={item.boxSize} onChange={event => onChange({ boxSize: event.target.value })} className="mt-1 block w-full rounded border border-border bg-white px-2 py-2 text-right text-sm outline-none focus:border-gold disabled:bg-cream"><option value="">选择</option>{boxSizeOptions.map(size => <option key={size} value={size}>{size} 支/盒</option>)}</select> : <input disabled={busy} value={item.boxSize} onChange={event => onChange({ boxSize: event.target.value })} inputMode="numeric" placeholder="目录未维护" className="mt-1 block w-full rounded border border-border px-2 py-2 text-right text-sm outline-none focus:border-gold disabled:bg-cream" />}</label><label className="text-[10px] font-semibold text-muted">盒数<input disabled={busy} value={item.boxQuantity} onChange={event => onChange({ boxQuantity: event.target.value })} inputMode="numeric" placeholder="待补" className="mt-1 block w-full rounded border border-border px-2 py-2 text-right text-sm outline-none focus:border-gold disabled:bg-cream" /></label><label className="text-[10px] font-semibold text-muted">每盒 RUB<input disabled={busy} value={item.unitPriceRubPerBox} onChange={event => onChange({ unitPriceRubPerBox: event.target.value })} inputMode="decimal" placeholder="待补" className="mt-1 block w-full rounded border border-border px-2 py-2 text-right text-sm outline-none focus:border-gold disabled:bg-cream" /></label></>}
    <div className="pb-1 text-right"><p className="text-[10px] font-semibold text-muted">小计</p><strong className="mt-1 block font-mono text-xs">{subtotal}</strong></div><button type="button" disabled={busy} onClick={onRemove} aria-label={`移除 ${name}`} className="mx-auto mb-0.5 grid h-8 w-8 place-items-center rounded text-muted hover:bg-accent-light hover:text-accent disabled:opacity-50"><Trash2 className="h-4 w-4" /></button>
  </article>;
}

function PayDialog({ purchase, accountId, businessDate, accounts, busy, error, onChange, onClose, onConfirm }: { purchase: PurchaseAction; accountId: string; businessDate: string; accounts: FundAccount[]; busy: boolean; error: string; onChange: (patch: { accountId?: string; businessDate?: string }) => void; onClose: () => void; onConfirm: () => void }) {
  return <div className="mx-auto max-w-lg"><DialogHeader title={`付款 · ${purchase.order_number || `采购单 #${purchase.id}`}`} subtitle="整单一次性付清；提交后生成付款事实，并锁定供应商、商品、数量和价格。" onClose={onClose} /><div className="px-5 py-5 sm:px-6"><div className="rounded border border-gold/30 bg-[#FFFDF7] p-4"><p className="text-[11px] text-muted">付款 RUB 总额</p><strong className="mt-1 block font-mono text-2xl">{displayRub(purchase.rub_total)}</strong><p className="mt-2 text-xs text-muted">第一版不支持部分付款；付款金额必须等于采购单 RUB 总额。</p></div>{!purchase.draft_complete && <p className="mt-3 rounded border border-[#E3C3C6] bg-[#FAF1F0] px-3 py-2 text-xs text-accent">该草稿尚未补全。请返回编辑，填写供应商、业务日期、商品盒规、盒数和每盒价格后再付款。</p>}<div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="text-xs font-semibold text-muted">付款日期<input type="date" value={businessDate} onChange={event => onChange({ businessDate: event.target.value })} disabled={busy} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold disabled:bg-cream" /></label><label className="text-xs font-semibold text-muted">付款 RUB 账户<select value={accountId} onChange={event => onChange({ accountId: event.target.value })} disabled={busy || !accounts.length} className="mt-1.5 w-full rounded border border-border bg-white px-3 py-2 text-sm outline-none focus:border-gold disabled:bg-cream"><option value="">{accounts.length ? '选择 RUB 账户' : '暂无可用 RUB 账户'}</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label></div><ModalError error={error} /></div><DialogFooter onClose={onClose} busy={busy} confirmLabel={`确认付款 ${displayRub(purchase.rub_total)}`} confirmDisabled={!purchase.draft_complete || !accountId || !businessDate} onConfirm={onConfirm} /></div>;
}

function ReceiveDialog({ purchase, businessDate, note, busy, error, onChange, onClose, onConfirm }: { purchase: PurchaseAction; businessDate: string; note: string; busy: boolean; error: string; onChange: (patch: { businessDate?: string; note?: string }) => void; onClose: () => void; onConfirm: () => void }) {
  return <div className="mx-auto max-w-lg"><DialogHeader title={`整单到货 · ${purchase.order_number || `采购单 #${purchase.id}`}`} subtitle="第一版只支持整单到货，不支持分批入库。" onClose={onClose} /><div className="px-5 py-5 sm:px-6"><p className="rounded border border-border bg-[#FFFDF9] px-3 py-3 text-sm leading-6 text-muted">确认后会为 <strong className="text-fg">{purchase.items.length} 个 SKU · {itemSticks(purchase.items)} 支</strong> 一次性创建 库存批次，并将已付款成本从在途转入库存。</p><div className="mt-4 grid gap-3"><label className="text-xs font-semibold text-muted">到货日期<input type="date" value={businessDate} onChange={event => onChange({ businessDate: event.target.value })} disabled={busy} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold disabled:bg-cream" /></label><label className="text-xs font-semibold text-muted">到货备注<textarea rows={2} value={note} onChange={event => onChange({ note: event.target.value })} disabled={busy} placeholder="例如：冷链外箱完好" className="mt-1.5 w-full resize-y rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold disabled:bg-cream" /></label></div><ModalError error={error} /></div><DialogFooter onClose={onClose} busy={busy} confirmLabel="确认整单到货" confirmDisabled={!businessDate} onConfirm={onConfirm} hint="生成 库存批次后，仅可通过受控的「撤回到货」回退。" /></div>;
}

function CancelDialog({ purchase, note, busy, error, onChange, onClose, onConfirm }: { purchase: PurchaseAction; note: string; busy: boolean; error: string; onChange: (note: string) => void; onClose: () => void; onConfirm: () => void }) {
  return <div className="mx-auto max-w-lg"><DialogHeader title={`取消采购单 · ${purchase.order_number || `采购单 #${purchase.id}`}`} subtitle="只允许取消尚未付款的草稿。" onClose={onClose} /><div className="px-5 py-5 sm:px-6"><p className="rounded border border-[#E3C3C6] bg-[#FAF1F0] px-3 py-3 text-sm leading-6 text-accent">取消后该草稿不可恢复。当前明细 {purchase.items.length} 个 SKU · {displayRub(purchase.rub_total)}，不会产生资金或库存变动。</p><label className="mt-4 block text-xs font-semibold text-muted">取消原因（选填）<textarea rows={2} value={note} onChange={event => onChange(event.target.value)} disabled={busy} placeholder="例如：供应商延迟，改期重新下单" className="mt-1.5 w-full resize-y rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold disabled:bg-cream" /></label><ModalError error={error} /></div><DialogFooter onClose={onClose} busy={busy} confirmLabel="确认取消采购单" confirmTone="danger" onConfirm={onConfirm} /></div>;
}

function ReverseDialog({ purchase, businessDate, note, busy, error, onChange, onClose, onNext }: { purchase: PurchaseAction; businessDate: string; note: string; busy: boolean; error: string; onChange: (patch: { businessDate?: string; note?: string }) => void; onClose: () => void; onNext: () => void }) {
  const count = purchase.items.reduce((sum, item) => sum + (item.batches?.length || 0), 0);
  return <div className="mx-auto max-w-lg"><DialogHeader title={`撤回到货 · ${purchase.order_number || `采购单 #${purchase.id}`}`} subtitle="低频危险操作，需要填写日期、原因并二次确认。" onClose={onClose} /><div className="px-5 py-5 sm:px-6"><p className="rounded border border-[#E3C3C6] bg-[#FAF1F0] px-3 py-3 text-sm leading-6 text-accent">将撤销当前到货产生的 <strong>{count} 条 库存批次</strong>，采购单会回到「已付款 · 待到货」。若批次已有出库，后端会拒绝操作以保护库存事实。</p><div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="text-xs font-semibold text-muted">撤回日期 *<input type="date" value={businessDate} onChange={event => onChange({ businessDate: event.target.value })} disabled={busy} className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold disabled:bg-cream" /></label><label className="text-xs font-semibold text-muted">撤回原因 *<input value={note} onChange={event => onChange({ note: event.target.value })} disabled={busy} placeholder="例如：到货短装，退回供应商" className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm outline-none focus:border-gold disabled:bg-cream" /></label></div><ModalError error={error} /></div><DialogFooter onClose={onClose} busy={busy} confirmLabel="继续 · 二次确认" confirmTone="danger" confirmDisabled={!businessDate || !note.trim()} onConfirm={onNext} hint="操作将完整写入账务与库存反向事实。" /></div>;
}

function ReverseConfirmDialog({ purchase, businessDate, note, busy, error, onBack, onClose, onConfirm }: { purchase: PurchaseAction; businessDate: string; note: string; busy: boolean; error: string; onBack: () => void; onClose: () => void; onConfirm: () => void }) {
  return <div className="mx-auto max-w-lg"><DialogHeader title="确认撤回到货" subtitle="请核对下面的不可逆影响。" onClose={onClose} /><div className="px-5 py-5 sm:px-6"><div className="rounded border border-[#E3C3C6] bg-[#FAF1F0] p-4 text-sm leading-6 text-accent"><strong>即将撤回 {purchase.order_number || `采购单 #${purchase.id}`} 的到货事实。</strong><dl className="mt-3 space-y-1 text-xs"><div className="flex justify-between gap-4"><dt>撤回日期</dt><dd className="font-mono text-fg">{businessDate}</dd></div><div className="flex justify-between gap-4"><dt>原因</dt><dd className="text-right text-fg">{note}</dd></div><div className="flex justify-between gap-4"><dt>影响库存</dt><dd className="font-mono text-fg">{itemSticks(purchase.items)} 支 / {purchase.items.reduce((sum, item) => sum + (item.batches?.length || 0), 0)} 条批次</dd></div></dl></div><ModalError error={error} /></div><footer className="flex justify-end gap-2 border-t border-border bg-[#FFFDF9] px-5 py-4 sm:px-6"><button type="button" disabled={busy} onClick={onBack} className="rounded border border-border bg-white px-3 py-2 text-sm font-semibold hover:border-gold disabled:opacity-50">返回修改</button><button type="button" disabled={busy} onClick={onConfirm} className="inline-flex items-center gap-1 rounded border border-accent bg-white px-4 py-2 text-sm font-semibold text-accent hover:bg-accent-light disabled:opacity-50"><Undo2 className="h-4 w-4" />{busy ? '撤回中…' : '确认撤回到货'}</button></footer></div>;
}

function DialogFooter({ onClose, busy, confirmLabel, confirmDisabled = false, confirmTone = 'primary', onConfirm, hint }: { onClose: () => void; busy: boolean; confirmLabel: string; confirmDisabled?: boolean; confirmTone?: 'primary' | 'danger'; onConfirm: () => void; hint?: string }) {
  return <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-[#FFFDF9] px-5 py-4 sm:px-6"><p className="max-w-sm text-[11px] text-muted">{hint}</p><div className="flex gap-2"><button type="button" disabled={busy} onClick={onClose} className="rounded border border-border bg-white px-3 py-2 text-sm font-semibold hover:border-gold disabled:opacity-50">取消</button><button type="button" disabled={busy || confirmDisabled} onClick={onConfirm} className={confirmTone === 'danger' ? 'rounded border border-accent bg-white px-4 py-2 text-sm font-semibold text-accent hover:bg-accent-light disabled:opacity-50' : 'rounded bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-hover disabled:opacity-50'}>{busy ? '处理中…' : confirmLabel}</button></div></footer>;
}
