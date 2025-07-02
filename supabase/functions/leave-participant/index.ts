// supabase/functions/leave-participant/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

console.log("Leave Participant function up and running!");

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
    const url = new URL(req.url);
    const pathParts = url.pathname.split("/");
    const participant_id = pathParts[pathParts.length - 1]; // e.g. /functions/v1/leave-participant/:participant_id

     if (!participant_id || participant_id === "leave-participant") { // Basic check
        return new Response(JSON.stringify({ error: "participant_id is required in path" }), {
            status: 400,
            headers: { "Content-Type": "application/json" },
        });
    }

    const { data, error } = await supabaseClient
      .from("participants")
      .update({ left_at: new Date().toISOString() })
      .eq("participant_id", participant_id)
      .select()
      .single();

    if (error) {
      console.error("Supabase error:", error);
      if (error.code === "PGRST116") { // PostgREST error for "No rows found"
        return new Response(JSON.stringify({ error: "Participant not found" }), {
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
         return new Response(JSON.stringify({ error: "Participant not found or no update made" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
    }

    return new Response(
      JSON.stringify({
        message: "Participant marked as left",
        participant_id: data.participant_id,
        left_at: data.left_at,
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
