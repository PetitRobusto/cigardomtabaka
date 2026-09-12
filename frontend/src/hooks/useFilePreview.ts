import { useEffect, useState } from 'react';

/** Read user-selected images asynchronously, discarding stale reads on replacement. */
export function useFilePreview(file: File | null) {
  const [value, setValue] = useState<{ file: File; url: string } | null>(null);
  useEffect(() => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') setValue({ file, url: reader.result });
    };
    reader.readAsDataURL(file);
    return () => { reader.onload = null; if (reader.readyState === FileReader.LOADING) reader.abort(); };
  }, [file]);
  return value?.file === file ? value?.url : undefined;
}
