import React, { useState, useEffect, useRef } from "react";
import { useDeepgramAudio } from "../hooks/useDeepgramAudio";

interface TeachToLearnProps {
  userId?: string;
}

interface TeachToLearnResponse {
  status: "question" | "response" | "complete" | "error";
  understanding_score?: number;
  is_complete?: boolean;
  text?: string;
  use_client_tts?: boolean;
  message?: string;
  audio?: string;
}

const TeachToLearn: React.FC<TeachToLearnProps> = ({ userId }) => {
  const [isTeaching, setIsTeaching] = useState<boolean>(false);
  const [topic, setTopic] = useState<string>("");
  const [understandingScore, setUnderstandingScore] = useState<number>(0);
  const [isComplete, setIsComplete] = useState<boolean>(false);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isPendingUserResponse, setIsPendingUserResponse] =
    useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const speechSynthesisRef = useRef<SpeechSynthesis | null>(null);

  // Set up Web Speech API
  useEffect(() => {
    // Check if browser supports speech synthesis
    if ("speechSynthesis" in window) {
      speechSynthesisRef.current = window.speechSynthesis;
    } else {
      setError(
        "Your browser does not support speech synthesis. Please try Chrome or Edge."
      );
    }

    return () => {
      // Cancel any ongoing speech when component unmounts
      if (speechSynthesisRef.current) {
        speechSynthesisRef.current.cancel();
      }
    };
  }, []);

  // Setup DeepGram for audio recording
  const {
    connect: connectToAudio,
    startRecording,
    stopRecording,
    isRecording,
    isConnected: isAudioConnected,
    error: audioError,
  } = useDeepgramAudio({
    apiUrl: "ws://localhost:8002/ws/audio-to-text",
    userId,
  });

  // Speak text using Web Speech API
  const speakText = (text: string): void => {
    if (!speechSynthesisRef.current) return;

    // Cancel any ongoing speech
    speechSynthesisRef.current.cancel();

    // Create utterance
    const utterance = new SpeechSynthesisUtterance(text);

    // Set properties
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    utterance.volume = 1.0;

    // Optional: Select voice (if available)
    const voices = speechSynthesisRef.current.getVoices();
    const preferredVoice = voices.find(
      (voice) =>
        voice.name.includes("Google") ||
        voice.name.includes("Female") ||
        voice.name.includes("Samantha")
    );

    if (preferredVoice) {
      utterance.voice = preferredVoice;
    }

    // Start speaking
    speechSynthesisRef.current.speak(utterance);

    // Set state while speaking
    setIsPendingUserResponse(false);

    // Listen for when speaking is done
    utterance.onend = () => {
      setIsPendingUserResponse(true);

      // Start recording after a short delay
      setTimeout(() => {
        if (isConnected && !isComplete) {
          startRecording();
        }
      }, 500);
    };
  };

  // Connect to teach-to-learn WebSocket
  const connectToTeachToLearn = (): void => {
    if (!topic) {
      setError("Please enter a topic to learn about");
      return;
    }

    try {
      const wsUrl = "ws://localhost:8002/ws/teach-to-learn";
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        setError(null);

        // Send initialization data
        ws.send(
          JSON.stringify({
            user_id: userId,
            topic: topic,
          })
        );

        // Also connect to audio WebSocket for recording
        connectToAudio();
      };

      ws.onmessage = (event: MessageEvent) => {
        const data: TeachToLearnResponse = JSON.parse(event.data);

        if (data.status === "error") {
          setError(data.message || "Unknown error");
          return;
        }

        // Update score if provided
        if (data.understanding_score !== undefined) {
          setUnderstandingScore(data.understanding_score);
        }

        // Handle complete status
        if (data.status === "complete") {
          setIsComplete(true);
          stopRecording();

          // Speak completion message
          if (data.text && data.use_client_tts) {
            speakText(data.text);
          }
          return;
        }

        // Handle response or question with text-to-speech
        if (
          (data.status === "response" || data.status === "question") &&
          data.text &&
          data.use_client_tts
        ) {
          // Stop any current recording while AI is speaking
          if (isRecording) {
            stopRecording();
          }

          // Speak the text
          speakText(data.text);

          // Update complete status if provided
          if (data.is_complete !== undefined) {
            setIsComplete(data.is_complete);
          }
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        setIsTeaching(false);
      };

      ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        setError("Connection error. Please try again.");
        setIsConnected(false);
      };

      setIsTeaching(true);
    } catch (err) {
      console.error("Error connecting to WebSocket:", err);
      setError("Failed to connect. Please try again.");
    }
  };

  // Handle start/stop button click
  const handleTeachToLearnToggle = (): void => {
    if (isTeaching) {
      // Stop the teaching session
      if (wsRef.current) {
        wsRef.current.send(JSON.stringify({ stop: true }));
      }
      stopRecording();
      setIsTeaching(false);
    } else {
      // Start a new teaching session
      connectToTeachToLearn();
    }
  };

  // Progress bar color based on score
  const getProgressColor = (): string => {
    if (understandingScore < 30) return "bg-red-500";
    if (understandingScore < 70) return "bg-yellow-500";
    return "bg-green-500";
  };

  return (
    <div className="p-4 max-w-3xl mx-auto bg-white rounded-lg shadow-md">
      <h1 className="text-2xl font-bold mb-4">Teach-to-Learn Mode</h1>

      {/* Connection status */}
      <div className="flex items-center mb-4">
        <span
          className={`inline-block w-3 h-3 rounded-full mr-2 ${
            isConnected ? "bg-green-500" : "bg-red-500"
          }`}
        ></span>
        <span>{isConnected ? "Connected" : "Disconnected"}</span>

        {isPendingUserResponse && isConnected && (
          <span className="ml-4 text-blue-500 animate-pulse">Listening...</span>
        )}
      </div>

      {/* Error message */}
      {(error || audioError) && (
        <div className="p-2 mb-4 bg-red-100 text-red-700 rounded">
          Error: {error || audioError}
        </div>
      )}

      {/* Topic input (only when not teaching) */}
      {!isTeaching && (
        <div className="mb-4">
          <label
            htmlFor="topic"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            What topic would you like to learn about?
          </label>
          <input
            type="text"
            id="topic"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Enter a topic (e.g., Neural Networks, Quantum Physics)"
            disabled={isTeaching}
          />
        </div>
      )}

      {/* Understanding progress bar */}
      {isTeaching && (
        <div className="mb-6">
          <div className="flex justify-between mb-1">
            <span className="text-sm font-medium">Understanding Progress</span>
            <span className="text-sm font-medium">{understandingScore}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-4">
            <div
              className={`h-4 rounded-full transition-all duration-500 ${getProgressColor()}`}
              style={{ width: `${understandingScore}%` }}
            ></div>
          </div>
        </div>
      )}

      {/* Start/Stop button */}
      <button
        onClick={handleTeachToLearnToggle}
        disabled={isTeaching && !isConnected}
        className={`px-4 py-2 rounded-md font-medium text-white ${
          isTeaching
            ? "bg-red-500 hover:bg-red-600"
            : "bg-blue-500 hover:bg-blue-600"
        } disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        {isTeaching ? "Stop Learning Session" : "Start Learning Session"}
      </button>

      {/* Completion message */}
      {isComplete && (
        <div className="mt-4 p-3 bg-green-100 text-green-800 rounded-md">
          <p className="font-medium">Learning complete! 🎉</p>
          <p>You've reached a good understanding of this topic.</p>
        </div>
      )}
    </div>
  );
};

export default TeachToLearn;
