import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Plus, Power, QrCode, X } from "lucide-react";
import {
  createPaymentMethod,
  fetchAccountingAccounts,
  fetchManagedPaymentMethods,
  setPaymentMethodActive,
} from "../../api";
import type { PaymentMethod } from "../../types";

const TYPES = [
  { value: "bank_card", label: "银行卡" },
  { value: "wechat", label: "微信" },
  { value: "alipay", label: "支付宝" },
] as const;
type MethodType = (typeof TYPES)[number]["value"];
const EMPTY = {
  method_type: "bank_card" as MethodType,
  label: "",
  bank_name: "",
  card_number: "",
  card_holder: "",
  account: "",
  remark: "",
  sort_order: "0",
  fund_account_id: "",
};
const typeLabel = (value: string) =>
  TYPES.find((item) => item.value === value)?.label || value;

export default function PaymentMethodManager() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY);
  const [qrFile, setQrFile] = useState<File | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const methods = useQuery({
    queryKey: ["managed-payment-methods"],
    queryFn: fetchManagedPaymentMethods,
  });
  const accounts = useQuery({
    queryKey: ["accounting-accounts"],
    queryFn: fetchAccountingAccounts,
  });
  const cnyAccounts = useMemo(
    () =>
      (accounts.data || []).filter(
        (account) => account.currency === "CNY" && account.is_active,
      ),
    [accounts.data],
  );
  const update = (field: keyof typeof EMPTY, value: string) =>
    setForm((previous) => ({ ...previous, [field]: value }));

  const resetForm = () => {
    setForm({
      ...EMPTY,
      fund_account_id: cnyAccounts[0] ? String(cnyAccounts[0].id) : "",
    });
    setQrFile(null);
    setError("");
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setMessage("");
    const fundAccountId =
      form.fund_account_id || (cnyAccounts[0] ? String(cnyAccounts[0].id) : "");
    if (!fundAccountId) {
      setError("请选择启用中的 CNY 资金账户");
      return;
    }
    if (
      (form.method_type === "wechat" || form.method_type === "alipay") &&
      !form.account.trim() &&
      !qrFile
    ) {
      setError("微信或支付宝至少填写收款账号或上传二维码");
      return;
    }
    setBusy(true);
    const payload = new FormData();
    Object.entries({ ...form, fund_account_id: fundAccountId }).forEach(
      ([key, value]) => payload.append(key, value),
    );
    if (qrFile) payload.append("qr_image", qrFile);
    try {
      await createPaymentMethod(payload);
      await queryClient.invalidateQueries({
        queryKey: ["managed-payment-methods"],
      });
      await queryClient.invalidateQueries({ queryKey: ["payment-methods"] });
      setMessage("收款方式已创建并启用");
      setShowForm(false);
      resetForm();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "收款方式创建失败",
      );
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (method: PaymentMethod) => {
    if (!method.id || method.is_active === undefined) return;
    const action = method.is_active ? "停用" : "重新启用";
    if (
      !window.confirm(
        `确认${action}“${method.label || method.bank_name || method.method_type}”？${method.is_active ? "停用后不会影响已经生成的收款链接。" : ""}`,
      )
    )
      return;
    setError("");
    setMessage("");
    setBusy(true);
    try {
      await setPaymentMethodActive(method.id, !method.is_active);
      await queryClient.invalidateQueries({
        queryKey: ["managed-payment-methods"],
      });
      await queryClient.invalidateQueries({ queryKey: ["payment-methods"] });
      setMessage(`收款方式已${method.is_active ? "停用" : "重新启用"}`);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "收款方式状态更新失败",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-display font-semibold text-fg">
            收款方式
          </h2>
          <p className="mt-1 text-sm text-muted">
            创建后不能编辑；更换卡号、二维码或账户请停用旧方式后重新创建。
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            resetForm();
            setShowForm(true);
          }}
          className="inline-flex items-center gap-2 rounded bg-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" />
          新建收款方式
        </button>
      </div>
      {message && (
        <p
          role="status"
          className="rounded border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800"
        >
          {message}
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
        </p>
      )}
      <div className="grid overflow-hidden rounded-lg border border-border bg-white shadow-sm sm:grid-cols-2 xl:grid-cols-4">
        <div className="border-b border-border p-4 sm:border-r xl:border-b-0">
          <div className="text-[11px] uppercase tracking-wider text-muted">
            已启用
          </div>
          <div className="mt-1 font-mono text-2xl font-semibold">
            {methods.data?.filter((method) => method.is_active).length ?? 0}
          </div>
          <div className="text-xs text-muted">可用于新收款链接</div>
        </div>
        <div className="border-b border-border p-4 xl:border-b-0 xl:border-r">
          <div className="text-[11px] uppercase tracking-wider text-muted">
            已停用
          </div>
          <div className="mt-1 font-mono text-2xl font-semibold">
            {methods.data?.filter((method) => !method.is_active).length ?? 0}
          </div>
          <div className="text-xs text-muted">保留审计和历史快照</div>
        </div>
        <div className="border-b border-border p-4 sm:border-b-0 sm:border-r">
          <div className="text-[11px] uppercase tracking-wider text-muted">
            收款渠道
          </div>
          <div className="mt-1 font-mono text-2xl font-semibold">3</div>
          <div className="text-xs text-muted">银行卡 · 微信 · 支付宝</div>
        </div>
        <div className="p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">
            CNY 账户
          </div>
          <div className="mt-1 font-mono text-2xl font-semibold">
            {cnyAccounts.length}
          </div>
          <div className="text-xs text-muted">当前可绑定账户</div>
        </div>
      </div>
      <div>
        <div className="grid gap-3 rounded-lg border border-border bg-white p-4 shadow-sm">
          {methods.isLoading && (
            <p className="rounded border border-border bg-white px-4 py-6 text-sm text-muted">
              正在加载收款方式…
            </p>
          )}
          {!methods.isLoading && methods.data?.length === 0 && (
            <p className="rounded border border-border bg-white px-4 py-6 text-sm text-muted">
              还没有收款方式，请先新建。
            </p>
          )}
          {methods.data?.map((method) => (
            <div
              key={method.id}
              className={`rounded border bg-white p-4 ${method.is_active ? "border-border" : "border-dashed border-border opacity-70"}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <div className="rounded bg-accent-light p-2 text-accent">
                    <Power className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-fg">
                        {method.label || typeLabel(method.method_type)}
                      </h3>
                      <span className="rounded-full bg-accent-light px-2 py-0.5 text-[11px] text-accent">
                        {typeLabel(method.method_type)}
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] ${method.is_active ? "bg-green-50 text-green-700" : "bg-gray-100 text-muted"}`}
                      >
                        {method.is_active ? "启用中" : "已停用"}
                      </span>
                    </div>
                    {method.method_type === "bank_card" ? (
                      <p className="mt-2 text-sm text-fg">
                        {method.bank_name} · {method.card_number} ·{" "}
                        {method.card_holder}
                      </p>
                    ) : (
                      <p className="mt-2 text-sm text-fg">
                        {method.account || "仅二维码收款"}
                        {method.qr_url ? " · 已上传二维码" : ""}
                      </p>
                    )}
                    <p className="mt-1 text-xs text-muted">
                      资金账户：
                      {method.fund_account_name ||
                        `#${method.fund_account_id || "未绑定"}`}{" "}
                      · 排序 {method.sort_order ?? 0}
                    </p>
                    {method.remark && (
                      <p className="mt-2 whitespace-pre-wrap text-xs text-muted">
                        备注：{method.remark}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {method.qr_url && (
                    <a
                      href={method.qr_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 rounded border border-border px-3 py-1.5 text-xs text-fg hover:border-accent"
                    >
                      <QrCode className="h-3.5 w-3.5" />
                      查看二维码
                    </a>
                  )}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => toggle(method)}
                    className="rounded border border-border px-3 py-1.5 text-xs font-semibold text-fg hover:border-accent disabled:opacity-50"
                  >
                    {method.is_active ? "停用" : "重新启用"}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
        {showForm && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="payment-method-form-title"
            className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 px-4 py-8 sm:items-center"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setShowForm(false);
            }}
          >
            <form
              onSubmit={submit}
              className="w-full max-w-2xl overflow-hidden rounded-lg border border-border bg-white shadow-2xl"
            >
              <div className="flex items-center justify-between border-b border-border px-5 py-4">
                <div>
                  <h2
                    id="payment-method-form-title"
                    className="font-display text-lg font-semibold"
                  >
                    新建收款方式
                  </h2>
                  <p className="mt-1 text-xs text-muted">
                    创建后字段锁定，替换请停用后重新创建。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  aria-label="关闭"
                  className="rounded p-1 text-muted hover:bg-accent-light hover:text-fg"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="grid gap-4 p-5 sm:grid-cols-2">
                <label className="text-xs font-medium text-muted">
                  类型
                  <select
                    required
                    value={form.method_type}
                    onChange={(event) =>
                      update("method_type", event.target.value as MethodType)
                    }
                    className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg"
                  >
                    <option value="bank_card">银行卡</option>
                    <option value="wechat">微信</option>
                    <option value="alipay">支付宝</option>
                  </select>
                </label>
                <label className="text-xs font-medium text-muted">
                  内部标签
                  <input
                    required
                    value={form.label}
                    onChange={(event) => update("label", event.target.value)}
                    className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg"
                    placeholder="例如：主银行卡"
                  />
                </label>
                {form.method_type === "bank_card" ? (
                  <>
                    <label className="text-xs font-medium text-muted">
                      银行名
                      <input
                        required
                        value={form.bank_name}
                        onChange={(event) =>
                          update("bank_name", event.target.value)
                        }
                        className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg"
                      />
                    </label>
                    <label className="text-xs font-medium text-muted">
                      卡号
                      <input
                        required
                        value={form.card_number}
                        onChange={(event) =>
                          update("card_number", event.target.value)
                        }
                        className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg"
                      />
                    </label>
                    <label className="text-xs font-medium text-muted">
                      持卡人
                      <input
                        required
                        value={form.card_holder}
                        onChange={(event) =>
                          update("card_holder", event.target.value)
                        }
                        className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg"
                      />
                    </label>
                  </>
                ) : (
                  <label className="text-xs font-medium text-muted sm:col-span-2">
                    收款账号（二维码和账号至少填一个）
                    <input
                      value={form.account}
                      onChange={(event) =>
                        update("account", event.target.value)
                      }
                      className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg"
                    />
                  </label>
                )}
                {form.method_type !== "bank_card" && (
                  <label className="text-xs font-medium text-muted sm:col-span-2">
                    收款二维码（可选，JPG/PNG/WebP，最大 5MB）
                    <input
                      type="file"
                      accept=".jpg,.jpeg,.png,.webp"
                      onChange={(event) =>
                        setQrFile(event.target.files?.[0] || null)
                      }
                      className="mt-1.5 block w-full text-sm text-fg"
                    />
                  </label>
                )}
                <label className="text-xs font-medium text-muted sm:col-span-2">
                  绑定 CNY 资金账户
                  <select
                    required
                    value={
                      form.fund_account_id ||
                      (cnyAccounts[0] ? String(cnyAccounts[0].id) : "")
                    }
                    onChange={(event) =>
                      update("fund_account_id", event.target.value)
                    }
                    className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg"
                  >
                    <option value="">请选择启用中的人民币账户</option>
                    {cnyAccounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-xs font-medium text-muted">
                  排序
                  <input
                    type="number"
                    min="0"
                    value={form.sort_order}
                    onChange={(event) =>
                      update("sort_order", event.target.value)
                    }
                    className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg"
                  />
                </label>
                <label className="text-xs font-medium text-muted sm:col-span-2">
                  收款备注
                  <textarea
                    value={form.remark}
                    onChange={(event) => update("remark", event.target.value)}
                    rows={3}
                    className="mt-1.5 w-full rounded border border-border px-3 py-2 text-sm text-fg"
                    placeholder="例如：转账请备注订单号"
                  />
                </label>
              </div>
              <div className="flex justify-end gap-2 border-t border-border px-5 py-4">
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="rounded border border-border px-4 py-2 text-sm"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={busy || accounts.isLoading}
                  className="inline-flex items-center gap-2 rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                >
                  {busy ? (
                    "保存中…"
                  ) : (
                    <>
                      <Check className="h-4 w-4" />
                      创建并启用
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
