// supabase/functions/create-call/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

console.log("Create Call function up and running!");

serve(async (req) => {
  // Create a Supabase client with the Auth context of the logged in user.
  // This assumes you have set SUPABASE_URL and SUPABASE_ANON_KEY in your secrets.
  const supabaseClient = createClient(
    Deno.env.get("SUPABASE_URL") ?? "",
    Deno.env.get("SUPABASE_ANON_KEY") ?? "",
    { global: { headers: { Authorization: req.headers.get("Authorization")! } } }
  );

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method Not Allowed" }), {
      status: 405,
      headers: { "Content-Type": "application/json" },
    });
  }

  try {
    const { room_name } = await req.json();

    const { data, error } = await supabaseClient
      .from("calls")
      .insert({ room_name: room_name || null }) // Ensure room_name is null if not provided
      .select()
      .single();

    if (error) {
      console.error("Supabase error:", error);
      return new Response(JSON.stringify({ error: error.message }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response(JSON.stringify(data), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  } catch (e) {
    console.error("Error processing request:", e);
    return new Response(JSON.stringify({ error: e.message || "Bad Request" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }
});
