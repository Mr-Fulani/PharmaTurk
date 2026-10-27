/**
 * Липкая панель «цена + В заявку» внизу карточки товара на телефоне.
 *
 * Что показывает кнопка панели:
 * - 'hidden'      — панели нет: услуга (заказ через мессенджеры) или товара нет в наличии;
 * - 'go_to_cart'  — товар уже добавлен: ведём в Список заявки;
 * - 'choose_size' — нужен размер: прокручиваем к выбору размера в основном блоке;
 * - 'add'         — добавляем в заявку прямо из панели.
 */
export function stickyBuyBarMode({ isService, outOfStock, sizeRequired, sizeSelected, added }) {
  if (isService || outOfStock) return 'hidden'
  if (added) return 'go_to_cart'
  if (sizeRequired && !sizeSelected) return 'choose_size'
  return 'add'
}

/**
 * Панель видна, пока основной блок с кнопкой не на экране (ещё ниже или уже выше).
 * rect — getBoundingClientRect() блока; bottomInset — высота самой панели,
 * чтобы панель не исчезала раньше, чем кнопка выйдет из-под неё.
 */
export function isActionBlockOffscreen(rect, viewportHeight, bottomInset = 0) {
  if (!rect) return false
  return rect.bottom <= 0 || rect.top >= viewportHeight - bottomInset
}
