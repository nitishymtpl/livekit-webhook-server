// supabase/functions/get-call-analytics/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient, SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

console.log("Get Call Analytics function up and running!");

// Helper function to calculate duration in seconds
function calculateDurationSeconds(start: string | null, end: string | null): number | null {
  if (!start || !end) {
    return null;
  }
  const startDate = new Date(start);
  const endDate = new Date(end);
  if (isNaN(startDate.getTime()) || isNaN(endDate.getTime())) {
    return null;
  }
  return Math.round((endDate.getTime() - startDate.getTime()) / 1000);
}

serve(async (req) => {
  const supabaseClient: SupabaseClient = createClient(
    Deno.env.get("SUPABASE_URL") ?? "",
    Deno.env.get("SUPABASE_ANON_KEY") ?? "",
    { global: { headers: { Authorization: req.headers.get("Authorization")! } } }
  );

  if (req.method !== "GET") {
    return new Response(JSON.stringify({ error: "Method Not Allowed" }), {
      status: 405,
      headers: { "Content-Type": "application/json" },
    });
  }

  try {
    const url = new URL(req.url);
    const pathParts = url.pathname.split("/");
    const call_id = pathParts[pathParts.length - 1]; // e.g. /functions/v1/get-call-analytics/:call_id

    if (!call_id || call_id === "get-call-analytics") {
      return new Response(JSON.stringify({ error: "call_id is required in path" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // 1. Fetch Call Details
    const { data: callData, error: callError } = await supabaseClient
      .from("calls")
      .select("call_id, room_name, created_at, finished_at")
      .eq("call_id", call_id)
      .single();

    if (callError) {
      console.error("Supabase error fetching call:", callError);
      if (callError.code === "PGRST116") {
        return new Response(JSON.stringify({ error: "Call not found" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ error: callError.message }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }
     if (!callData) {
        return new Response(JSON.stringify({ error: "Call not found" }), {
            status: 404,
            headers: { "Content-Type": "application/json" },
        });
    }


    const overall_call_duration_seconds = calculateDurationSeconds(callData.created_at, callData.finished_at);

    // 2. Fetch Participant Details
    const { data: participantsData, error: participantsError } = await supabaseClient
      .from("participants")
      .select("participant_id, participant_name, joined_at, left_at")
      .eq("call_id", call_id)
      .order("joined_at", { ascending: true });

    if (participantsError) {
      console.error("Supabase error fetching participants:", participantsError);
      return new Response(JSON.stringify({ error: participantsError.message }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }

    const participantsAnalytics = (participantsData || []).map(p => ({
      participant_id: p.participant_id,
      participant_name: p.participant_name,
      joined_at: p.joined_at,
      left_at: p.left_at,
      duration_in_call_seconds: calculateDurationSeconds(p.joined_at, p.left_at),
    }));

    const responsePayload = {
      call_id: callData.call_id,
      room_name: callData.room_name,
      call_created_at: callData.created_at,
      call_finished_at: callData.finished_at,
      overall_call_duration_seconds: overall_call_duration_seconds,
      participants: participantsAnalytics,
    };

    return new Response(JSON.stringify(responsePayload), {
      status: 200,
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
