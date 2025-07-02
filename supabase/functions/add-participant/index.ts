// supabase/functions/add-participant/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

console.log("Add Participant function up and running!");

serve(async (req) => {
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
    const { call_id, participant_name } = await req.json();

    if (!call_id || !participant_name) {
      return new Response(
        JSON.stringify({ error: "call_id and participant_name are required" }),
        {
          status: 400,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Optional: Check if call_id exists in 'calls' table first
    // const { data: callData, error: callError } = await supabaseClient
    //   .from('calls')
    //   .select('call_id')
    //   .eq('call_id', call_id)
    //   .maybeSingle();

    // if (callError || !callData) {
    //   return new Response(JSON.stringify({ error: "Call not found" }), {
    //     status: 404, headers: { 'Content-Type': 'application/json' }
    //   });
    // }

    const { data, error } = await supabaseClient
      .from("participants")
      .insert({ call_id, participant_name })
      .select()
      .single();

    if (error) {
      console.error("Supabase error:", error);
       // Check for foreign key violation if call_id does not exist
      if (error.code === '23503' && error.details?.includes('call_id')) {
        return new Response(JSON.stringify({ error: `Call with id ${call_id} not found.` }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }
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
