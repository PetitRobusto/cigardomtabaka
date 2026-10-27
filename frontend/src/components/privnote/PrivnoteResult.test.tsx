// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createPrivnoteQrImage } from '../../lib/privnoteQr';
import PrivnoteResult from './PrivnoteResult';

vi.mock('../../lib/privnoteQr', () => ({ createPrivnoteQrImage: vi.fn() }));
const url = 'https://example.com/p/private-token/?source=a%2Fb#section';
const image = 'data:image/png;base64,cXItcHJldmlldw==';
const props = { url, token: 'private-token', onCreateNew: vi.fn(), onViewRecords: vi.fn() };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(createPrivnoteQrImage).mockResolvedValue(image);
  vi.stubGlobal('fetch', vi.fn());
  vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('encodes and copies the exact link without opening it, and downloads the displayed PNG', async () => {
  const screen = render(<PrivnoteResult {...props} />);
  const qr = await screen.findByRole('img', { name: '链接二维码' });
  expect(createPrivnoteQrImage).toHaveBeenCalledWith(url);
  expect(qr.getAttribute('src')).toBe(image);
  fireEvent.click(screen.getByRole('button', { name: '复制链接' }));
  await screen.findByRole('button', { name: '已复制' });
  expect(navigator.clipboard.writeText).toHaveBeenCalledWith(url);
  const download = screen.getByRole('link', { name: '保存二维码' });
  expect(download.getAttribute('href')).toBe(image);
  expect(download.getAttribute('download')).toBe('CigarDomTabaka-二维码.png');
  expect(fetch).not.toHaveBeenCalled();
});

it('keeps the link usable while generating and after QR failure, and retries only the QR', async () => {
  vi.mocked(createPrivnoteQrImage).mockRejectedValueOnce(new Error('canvas unavailable'));
  const screen = render(<PrivnoteResult {...props} />);
  await screen.findByText('二维码生成失败，链接仍可使用。');
  fireEvent.click(screen.getByRole('button', { name: '复制链接' }));
  await screen.findByRole('button', { name: '已复制' });
  fireEvent.click(screen.getByRole('button', { name: '重试二维码' }));
  await screen.findByRole('img', { name: '链接二维码' });
  expect(createPrivnoteQrImage).toHaveBeenCalledTimes(2);
  expect(props.onCreateNew).not.toHaveBeenCalled();
  expect(fetch).not.toHaveBeenCalled();
});

it('reports clipboard failure honestly and leaves the full link selectable', async () => {
  vi.mocked(navigator.clipboard.writeText).mockRejectedValue(new Error('denied'));
  const screen = render(<PrivnoteResult {...props} />);
  fireEvent.click(screen.getByRole('button', { name: '复制链接' }));
  await screen.findByText('复制失败，请选择上方链接手动复制。');
  expect(screen.queryByRole('button', { name: '已复制' })).toBeNull();
  expect(screen.getByText(url)).toBeTruthy();
});

it('falls back to copying the exact link when the clipboard API is unavailable', async () => {
  vi.mocked(navigator.clipboard.writeText).mockRejectedValue(new Error('denied'));
  const fallback = vi.fn(() => {
    expect((document.querySelector('textarea') as HTMLTextAreaElement).value).toBe(url);
    return true;
  });
  Object.defineProperty(document, 'execCommand', { configurable: true, value: fallback });
  try {
    const screen = render(<PrivnoteResult {...props} />);
    const button = screen.getByRole('button', { name: '复制链接' });
    button.focus();
    fireEvent.click(button);
    await screen.findByRole('button', { name: '已复制' });
    expect(fallback).toHaveBeenCalledWith('copy');
    expect(document.querySelector('textarea')).toBeNull();
    expect(document.activeElement).toBe(button);
  } finally {
    Reflect.deleteProperty(document, 'execCommand');
  }
});

it('zooms locally, traps keyboard focus, closes with Escape and restores the trigger', async () => {
  const screen = render(<PrivnoteResult {...props} />);
  await screen.findByRole('img', { name: '链接二维码' });
  const trigger = screen.getByRole('button', { name: '放大链接二维码' });
  trigger.focus();
  fireEvent.click(trigger);
  const dialog = screen.getByRole('dialog', { name: '链接二维码' });
  expect(dialog.contains(document.activeElement)).toBe(true);
  const close = screen.getByRole('button', { name: '关闭二维码' });
  const save = dialog.querySelector('a')!;
  close.focus();
  fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
  expect(document.activeElement).toBe(save);
  fireEvent.keyDown(document, { key: 'Tab' });
  expect(document.activeElement).toBe(close);
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(document.activeElement).toBe(trigger);
  expect(fetch).not.toHaveBeenCalled();
});

it('does not show an old image when the link changes while generation is pending', async () => {
  let resolveOld!: (image: string) => void;
  vi.mocked(createPrivnoteQrImage).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }));
  const screen = render(<PrivnoteResult {...props} />);
  screen.rerender(<PrivnoteResult {...props} url="https://example.com/p/new/" />);
  await screen.findByRole('img', { name: '链接二维码' });
  await act(async () => resolveOld('data:image/png;base64,b2xk'));
  await waitFor(() => expect(screen.getByRole('img', { name: '链接二维码' }).getAttribute('src')).toBe(image));
});
