/**
 * Онлайн-оплата (крипта) выключена: каждый заказ — заявка менеджеру, способ оплаты
 * согласуется с клиентом по выбранному каналу связи. Включить:
 * NEXT_PUBLIC_ONLINE_PAYMENTS_ENABLED=true (и ORDER_ONLINE_PAYMENTS_ENABLED=true на бэкенде).
 */
export const ONLINE_PAYMENTS_ENABLED = process.env.NEXT_PUBLIC_ONLINE_PAYMENTS_ENABLED === 'true'
