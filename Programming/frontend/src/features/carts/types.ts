export type StockWarning = {
  reason: string;
  availableQuantity: number;
  missingQuantity: number;
};

export type CartStockError = StockWarning & {
  cartItemId?: string;
  productId?: string;
  productTitle?: string;
  requestedQuantity?: number;
};

export type CartItem = {
  cartItemId: string;
  productId: string;
  productTitle: string;
  productType: string;
  imageUrl: string;
  unitPrice: string;
  quantity: number;
  lineSubtotal: string;
  stockQuantity: number;
  productStatus: string;
  stockWarning: StockWarning | null;
};

export type Cart = {
  cartId: string;
  cartToken: string;
  status: string;
  items: CartItem[];
  subtotalExclVat: string;
  totalItems: number;
  canPlaceOrder: boolean;
  stockErrors: CartStockError[];
};
