export const BUYER_STATUS_META = {
  pending: {
    label: 'Ожидает',
    tone: 'neutral',
    color: '#555555',
    iconName: 'IconStatusPending',
  },
  in_order: {
    label: 'На рассмотрении',
    tone: 'pending',
    color: '#F59E0B',
    iconName: 'IconStatusInOrder',
  },
  paid: {
    label: 'Оплачен',
    tone: 'progress',
    color: '#15ffcc',
    iconName: 'IconStatusPaid',
  },
  shipped: {
    label: 'Отправлен',
    tone: 'progress',
    color: '#12efac',
    iconName: 'IconStatusShipped',
  },
  arrived: {
    label: 'Доставлен',
    tone: 'complete',
    color: '#22C55E',
    iconName: 'IconStatusArrived',
  },
}
