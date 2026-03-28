const STATE_ICONS = {
  progress: 'IconStateRetry',
  empty: 'IconStateEmpty',
  error: 'IconStateAlert',
  success: 'IconStateSuccess',
}

export const BUYER_STATE_COPY = {
  history: {
    loading: {
      eyebrow: 'История',
      title: 'Загружаем историю',
      body: 'Подтягиваем последние расчёты и быстрый повтор по товарам.',
      iconName: STATE_ICONS.progress,
    },
    empty: {
      eyebrow: 'История',
      title: 'История пока пуста',
      body: 'Сделайте первый расчёт в Калькуляторе — он появится здесь.',
      iconName: STATE_ICONS.empty,
    },
    error: {
      eyebrow: 'История',
      title: 'Не удалось показать историю',
      body: 'Не удалось загрузить историю. Попробуйте ещё раз.',
      actionLabel: 'Повторить',
      iconName: STATE_ICONS.error,
    },
  },
  orders: {
    loading: {
      eyebrow: 'Заявки',
      title: 'Загружаем заявки',
      body: 'Подтягиваем товары, которые готовы к оформлению.',
      iconName: STATE_ICONS.progress,
    },
    empty: {
      eyebrow: 'Заявки',
      title: 'Заявок пока нет',
      body: 'Добавьте товары из корзины в заявку — они появятся здесь.',
      iconName: STATE_ICONS.empty,
    },
    fetchError: {
      eyebrow: 'Заявки',
      title: 'Не удалось загрузить заявки',
      body: 'Не удалось загрузить заявки. Попробуйте ещё раз.',
      actionLabel: 'Повторить',
      iconName: STATE_ICONS.error,
    },
    submitSuccess: {
      eyebrow: 'Заявка отправлена',
      title: 'Заказ оформлен',
      body: 'Мы передали заявку администратору. Следить за статусом можно в разделе «Мои заказы».',
      iconName: STATE_ICONS.success,
    },
  },
  myOrders: {
    loading: {
      eyebrow: 'Мои заказы',
      title: 'Загружаем заказы',
      body: 'Собираем последние изменения по статусам и отправке.',
      iconName: STATE_ICONS.progress,
    },
    empty: {
      eyebrow: 'Мои заказы',
      title: 'Заказов пока нет',
      body: 'Оформленные заказы появятся здесь после подтверждения.',
      iconName: STATE_ICONS.empty,
    },
    fetchError: {
      eyebrow: 'Мои заказы',
      title: 'Не удалось загрузить заказы',
      body: 'Не удалось загрузить заказы. Попробуйте ещё раз.',
      actionLabel: 'Повторить',
      iconName: STATE_ICONS.error,
    },
    statusMessages: {
      in_order: 'Заявка на рассмотрении — администратор свяжется с вами.',
      paid: 'Товар оплачен, ожидайте отправки.',
      shipped: 'Товар в пути и движется к выдаче.',
      arrived: 'Товар доставлен. Свяжитесь с администратором для получения.',
    },
  },
  cart: {
    loading: {
      eyebrow: 'Корзина',
      title: 'Загружаем корзину',
      body: 'Собираем товары, суммы и подготовленные позиции к заявке.',
      iconName: STATE_ICONS.progress,
    },
    empty: {
      eyebrow: 'Корзина',
      title: 'Корзина пока пуста',
      body: 'Добавьте товары из Калькулятора — они появятся здесь.',
      iconName: STATE_ICONS.empty,
    },
    fetchError: {
      eyebrow: 'Корзина',
      title: 'Не удалось загрузить корзину',
      body: 'Не удалось получить товары корзины. Попробуйте ещё раз.',
      actionLabel: 'Повторить',
      iconName: STATE_ICONS.error,
    },
    detailLoading: {
      eyebrow: 'Детали товара',
      title: 'Загружаем расчёт',
      body: 'Подтягиваем карточку товара, варианты и свежую стоимость.',
      iconName: STATE_ICONS.progress,
    },
    detailError: {
      eyebrow: 'Детали товара',
      title: 'Не удалось загрузить товар',
      body: 'Попробуйте открыть позицию ещё раз.',
      actionLabel: 'Закрыть',
      iconName: STATE_ICONS.error,
    },
  },
  calculator: {
    linkError: {
      eyebrow: 'Калькулятор',
      title: 'Ссылка не открылась',
      body: 'Не удалось загрузить товар. Проверьте ссылку и попробуйте снова.',
      actionLabel: 'Попробовать снова',
      iconName: STATE_ICONS.error,
    },
    searchEmpty: {
      eyebrow: 'Поиск',
      title: 'Ничего не нашли',
      body: 'Попробуйте уточнить запрос или использовать другое название товара.',
      iconName: STATE_ICONS.empty,
    },
    searchError: {
      eyebrow: 'Поиск',
      title: 'Не удалось выполнить поиск',
      body: 'Маркетплейс не ответил на запрос. Попробуйте ещё раз чуть позже.',
      actionLabel: 'Повторить поиск',
      iconName: STATE_ICONS.error,
    },
    resultSuccess: {
      eyebrow: 'Расчёт готов',
      title: 'Итоговая цена рассчитана',
      body: 'Проверьте состав цены, сравните маркетплейсы и решите, добавлять ли товар в корзину.',
      iconName: STATE_ICONS.success,
    },
    addToCartSuccess: {
      eyebrow: 'Товар в корзине',
      title: 'Позиция сохранена',
      body: 'Можно продолжить расчёт или позже перейти к оформлению заявки из корзины.',
      iconName: STATE_ICONS.success,
    },
  },
}
