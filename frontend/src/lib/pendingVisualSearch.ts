// Фото, выбранное значком камеры в шапке, передаётся блоку «Поиск по фото» на /search
// без URL и хранилищ: File живёт только в памяти вкладки.
let pendingFile: File | null = null
let listener: (() => void) | null = null

export function setPendingVisualFile(file: File): void {
  pendingFile = file
  listener?.()
}

export function takePendingVisualFile(): File | null {
  const file = pendingFile
  pendingFile = null
  return file
}

export function onPendingVisualFile(callback: (() => void) | null): void {
  listener = callback
}
