import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_ANON_KEY

// Anon key is read-only here (RLS allows SELECT only). Writes go through the
// service-role key in the Python CLIs, which bypass RLS.
export const configured = Boolean(url && key)
export const supabase = configured ? createClient(url, key) : null
