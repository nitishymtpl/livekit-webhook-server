// supabase/functions/finish-call/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

console.log("Finish Call function up and running!");

serve(async (req) => {
  const supabaseClient = createClient(
    Deno.env.get("SUPABASE_URL") ?? "",
    Deno.env.get("SUPABASE_ANON_KEY") ?? "",
    { global: { headers: { Authorization: req.headers.get("Authorization")! } } }
  );

  if (req.method !== "PUT") {
    return new Response(JSON.stringify({ error: "Method Not Allowed" }), {
      status: 405,
      headers: { "Content-Type": "application/json" },
    });
  }

  try {
    // Supabase Edge Functions typically get path variables from the URL pattern
    // defined when deploying the function, e.g., /functions/v1/finish-call/:call_id
    // Here, we'll assume the call_id is the last part of the path.
    const url = new URL(req.url);
    const pathParts = url.pathname.split("/");
    const call_id = pathParts[pathParts.length - 1]; // Or -2 if there's a trailing slash in deploy

    if (!call_id || call_id === "finish-call") { // Basic check
        return new Response(JSON.stringify({ error: "call_id is required in path" }), {
            status: 400,
            headers: { "Content-Type": "application/json" },
        });
    }

    const { data, error } = await supabaseClient
      .from("calls")
      .update({ finished_at: new Date().toISOString() })
      .eq("call_id", call_id)
      .select()
      .single();

    if (error) {
      console.error("Supabase error:", error);
      if (error.code === "PGRST116") { // PostgREST error for "No rows found"
        return new Response(JSON.stringify({ error: "Call not found" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ error: error.message }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (!data) {
         return new Response(JSON.stringify({ error: "Call not found or no update made" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
    }

    return new Response(
      JSON.stringify({
        message: "Call marked as finished",
        call_id: data.call_id,
        finished_at: data.finished_at,
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }
    );
  } catch (e) {
    console.error("Error processing request:", e);
    return new Response(JSON.stringify({ error: e.message || "Bad Request" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }
});
