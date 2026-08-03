export type Role = "CUSTOMER" | "PRODUCT_MANAGER" | "ADMIN";

export type AuthUser = {
  userId: string;
  username: string;
  email: string;
  status: "ACTIVE" | "DEACTIVATED" | "BLOCKED";
  roles: Role[];
};

export type AuthResponse = {
  token: string;
  user: AuthUser;
};

export type LoginPayload = {
  username: string; // accepts email or username (backend matches both)
  password: string;
};

export type RegisterPayload = {
  username: string;
  email: string;
  password: string;
  fullName?: string;
  phone?: string;
};
