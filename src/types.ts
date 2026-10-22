export type Book = { id: number; title: string; author: string; category: string; isbn?: string; publisher?: string; year?: string; description?: string; copies: number; available: number; code: string }
export type LoanStatus = 'Ativo' | 'Atrasado' | 'Devolvido'
export type Loan = { id: number; student: string; registration: string; className: string; book: string; borrowed: string; due: string; status: LoanStatus }
export type Student = { id: number; name: string; registration: string; className: string; status: 'Ativo' | 'Inativo' }
