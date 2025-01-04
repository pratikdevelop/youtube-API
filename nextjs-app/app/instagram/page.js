// pages/download.js
'use client'

import { useState, useEffect } from "react";

export default function DownloadPage() {
  const [videoUrl, setVideoUrl] = useState("");
  const [responseMessage, setResponseMessage] = useState("");
  const [videoList, setVideoList] = useState([]);

  useEffect(() => {
    fetchProcessedVideos(); // Initial fetch for processed videos
  }, []);

  async function fetchProcessedVideos() {
    try {
      const response = await fetch("http://localhost:5000/list-videos?type=instagram");
      const data = await response.json();
      setVideoList(data);
    } catch (error) {
      console.error("Error fetching processed videos:", error);
    }
  }

  const handleFormSubmit = async (e) => {
    e.preventDefault();
    setResponseMessage("Processing...");

    try {
      const response = await fetch('http://localhost:5000/download-instagram', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: videoUrl }),
      });

      if (response.ok) {
        setResponseMessage("Video processed successfully!");
        fetchProcessedVideos(); // Refresh the list after processing
      } else {
        setResponseMessage("Error processing video.");
      }
    } catch (error) {
      setResponseMessage(`Error: ${error}`);
    }
  };

  const handleDeleteVideo = async (videoId) => {
    try {
      const deleteResponse = await fetch(`http://localhost:5000/delete-video/${videoId}`, { method: 'DELETE' });
      if (deleteResponse.ok) {
        setVideoList(videoList.filter((video) => video.id !== videoId));
        alert("Video deleted successfully.");
      } else {
        alert("Failed to delete the video.");
      }
    } catch (error) {
      console.error("Error deleting video:", error);
      alert("Error deleting video.");
    }
  };

  const handleSelectVideo = (videoId) => {
    // Handle select/unselect logic for videos
    console.log(`Video ${videoId} selected/unselected.`);
  };

  const handleDownloadFile = async (fileKey) => {
    try {
      const response = await fetch(`http://localhost:5000/get-presigned-url?file_key=${fileKey}`);
      const data = await response.json();
      if (data.url) {
        const a = document.createElement("a");
        a.href = data.url;
        a.download = fileKey.split("/").pop();
        document.body.appendChild(a);
        a.click();
        a.remove();
      }
    } catch (error) {
      console.error("Error fetching pre-signed URL:", error);
    }
  };

  const getVideoID = (url) => {
    console.log(
      "Video ID from URL: " + url
    );
    
    const match = url.match(/https:\/\/www\.instagram\.com\/(?:reel|p)\/([^\/?]+)/);

    if (match) {
      const reelId = match[1]; // The Reel ID
      return reelId
    } else {
     return null
    }

  }

  return (
    <div className="flex flex-col space-y-4 p-12 mx-28">
      <h1 className="text-3xl font-bold text-gray-800 mb-6">Download Instagram Videos/Images</h1>
      <p className="text-lg text-gray-600 mb-4">Enter the Instagram URL to download the video or image</p>
      <form id="videoForm" className="mb-6 space-y-6" onSubmit={handleFormSubmit}>
        <input
          type="url"
          id="videoUrl"
          value={videoUrl}
          onChange={(e) => setVideoUrl(e.target.value)}
          placeholder="Enter Instagram URL"
          className="w-full p-3 border border-gray-300 rounded-md"
          required
        />
        <button
          type="submit"
          className="w-full bg-blue-600 text-white py-3 rounded-md hover:bg-blue-700 transition duration-300"
        >
          Download Video/Image
        </button>
      </form>
      <div id="responseMessage" className="text-lg text-gray-600 mb-4">
        {responseMessage}
      </div>

      <div className="flex w-full items-center justify-between" id="video-container">
        <h2 className="text-3xl font-bold text-gray-800 mb-6">
          <a href="#" className="text-blue-600 hover:text-blue-800">Processed Videos</a>
        </h2>
      </div>
      <ul id="videoList" className="mt-6 space-y-4 flex space-x-4 flex-wrap">
        {videoList.map((video) => (
          <li key={video.id} className="bg-white p-6 rounded-lg shadow-lg mb-4 relative flex flex-col w-4/12">
            {video.video_url ? (
              <div>
                <iframe
                  width="400"
                  height="345"
                  src={`https://www.instagram.com/reel/${getVideoID(video.video_url)}/embed`}
                  frameBorder="0"
                  allowFullScreen
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen;"
                ></iframe>
              </div>
            ) : (
              <p>No video URL available</p>
            )}

            {video.segment_length && (
              <p>Segment Length: {video.segment_length} seconds</p>
            )}

            <p>Created At: {video.created_at}</p>

            <div className="mt-2 flex items-center space-x-4">
              <button
                className="text-white bg-red-600 hover:bg-red-700 px-4 py-2 mt-2 rounded"
                onClick={() => handleDeleteVideo(video.id)}
              >
                <i className="fa fa-trash-o"></i> Delete
              </button>

              <button
                className="video-select-btn px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-300"
                onClick={() => handleSelectVideo(video.id)}
              >
                Select
              </button>

              {video.file_urls && video.file_urls.length > 0 && (
                <div className="flex flex-wrap space-y-6 text-sm">
                  <select
                    className="text-blue-500 py-3 px-4 rounded w-full"
                    onChange={(e) => handleDownloadFile(e.target.value)}
                  >
                    <option disabled selected>
                      Select a file to download
                    </option>
                    {video.file_urls.map((fileUrl, index) => (
                      <option key={index} value={fileUrl}>
                        Download File {index + 1}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
