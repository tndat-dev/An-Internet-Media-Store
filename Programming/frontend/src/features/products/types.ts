export type ProductType = "BOOK" | "CD" | "DVD" | "NEWSPAPER";

export type ProductStatus = "ACTIVE" | "DEACTIVATED" | "DELETED";

export type ProductTypeDetails = Record<string, string | number | null>;

export type Product = {
  product_id: string;
  product_type: ProductType;
  title: string;
  category: string;
  general_description: string;
  height: string;
  width: string;
  length: string;
  weight: string;
  barcode: string;
  image_url: string;
  original_value: string;
  current_price: string;
  stock_quantity: number;
  status: ProductStatus;
  type_details: ProductTypeDetails;
  created_at: string;
  updated_at: string;
};

export type ProductPayload = {
  product_type: ProductType;
  title: string;
  category: string;
  general_description: string;
  height: string;
  width: string;
  length: string;
  weight: string;
  barcode: string;
  image_url?: string;
  original_value: string;
  current_price: string;
  stock_quantity: number;
  status?: ProductStatus;
  type_details: ProductTypeDetails;
  stock_adjustment_reason?: string;
};

export type BookDetails = {
  authors?: string;
  cover_type?: string;
  publisher?: string;
  publication_date?: string | null;
  pages?: number | null;
  language?: string;
  genre?: string;
};

export type CDDetails = {
  artists?: string;
  record_label?: string;
  tracklist?: string;
  genre?: string;
  release_date?: string | null;
};

export type DVDDetails = {
  disc_type?: string;
  director?: string;
  runtime_minutes?: number | null;
  studio?: string;
  language?: string;
  subtitles?: string;
  release_date?: string | null;
  genre?: string;
};

export type NewspaperDetails = {
  editor_in_chief?: string;
  publisher?: string;
  publication_date?: string | null;
  issue_number?: string;
  publication_frequency?: string;
  issn?: string;
  language?: string;
  sections?: string;
};

type CustomerProductBase = {
  product_id: string;
  title: string;
  category: string;
  description: string;
  image_url: string;
  price: string;
  stock_quantity: number;
  status: ProductStatus;
  is_available: boolean;
  height: string;
  width: string;
  length: string;
  weight: string;
  barcode: string;
};

export type CustomerProduct =
  | (CustomerProductBase & {
      product_type: "BOOK";
      type_details: BookDetails;
    })
  | (CustomerProductBase & {
      product_type: "CD";
      type_details: CDDetails;
    })
  | (CustomerProductBase & {
      product_type: "DVD";
      type_details: DVDDetails;
    })
  | (CustomerProductBase & {
      product_type: "NEWSPAPER";
      type_details: NewspaperDetails;
    });

export type CustomerProductFilters = {
  search?: string;
  category?: string;
  minPrice?: string;
  maxPrice?: string;
  sort?: "" | "title" | "newest" | "price_asc" | "price_desc";
};

// Mirrors DRF PageNumberPagination response shape.
export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type ProductHistoryAction = "CREATE" | "UPDATE" | "DELETE" | "DEACTIVATE" | "STOCK_ADJUST";

// Mirrors ProductHistorySerializer (apps/products/serializers.py).
export type ProductHistoryEntry = {
  history_id: string;
  product_id: string;
  product_title: string;
  action_type: ProductHistoryAction;
  performed_by: string | null;
  reason: string;
  changes: {
    before?: Record<string, string | number | null>;
    after?: Record<string, string | number | null>;
  };
  created_at: string;
};
