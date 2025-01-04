'use client'
import { useEffect, useState } from "react";

const Youtube = () => {
  const [videos, setVideos] = useState([]);
  const [selectedVideos, setSelectedVideos] = useState([]);
  const [videoUrl, setVideoUrl] = useState("");
  const [segmentLength, setSegmentLength] = useState(0);


  useEffect(() => {
    fetchProcessedVideos();
  }, []);

  const fetchProcessedVideos = async () => {
    try {
      const response = await fetch("http://localhost:5000/list-videos?type=youtube");
      const data = await response.json();
      setVideos(data);
    } catch (error) {
      console.error("Error fetching processed videos:", error);
    }
  };

  const handleDeleteSelected = async () => {
    if (selectedVideos.length === 0) {
      alert("No videos selected for deletion.");
      return;
    }

    try {
      const deleteResponse = await fetch("http://localhost:5000/delete-videos", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ videoIds: selectedVideos }),
      });

      if (deleteResponse.ok) {
        // Remove the deleted videos from the state
        setVideos(videos.filter((video) => !selectedVideos.includes(video.id)));
        setSelectedVideos([]);
        alert("Selected videos deleted successfully.");
      } else {
        alert("Failed to delete selected videos.");
      }
    } catch (error) {
      console.error("Error deleting videos:", error);
      alert("Error deleting videos.");
    }
  };

  const handleToggleSelect = (videoId) => {
    setSelectedVideos((prevSelectedVideos) =>
      prevSelectedVideos.includes(videoId)
        ? prevSelectedVideos.filter((id) => id !== videoId)
        : [...prevSelectedVideos, videoId]
    );
  };

  const handleDeleteVideo = async (videoId) => {
    try {
      const deleteResponse = await fetch(`http://localhost:5000/delete-video/${videoId}`, {
        method: "DELETE",
      });

      if (deleteResponse.ok) {
        setVideos(videos.filter((video) => video.id !== videoId));
        alert("Video deleted successfully.");
      } else {
        alert("Failed to delete the video.");
      }
    } catch (error) {
      console.error("Error deleting video:", error);
      alert("Error deleting video.");
    }
  };

  const processVideo = async () => {

    try {
      const response = await fetch("http://localhost:5000/process-video", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ url: videoUrl, segment_length: segmentLength }),
      });

      if (response.ok) {
        responseMessage.textContent =
          "Video processed successfully! Check below for the download link.";
        fetchProcessedVideos(); // Refresh the list after processing
      } else {
        responseMessage.textContent = `Error processing video: ${response.statusText}`;
      }
    } catch (error) {
      responseMessage.textContent = `Error: ${error.message}`;
    }
  }
  const downloadShort = (fileKey) => {
    const key = getFileKeyFromUrl(fileKey);

    // Use the fileKey to generate the presigned URL and initiate the download
    fetch(`http://localhost:5000/get-presigned-url?file_key=${key}`)
      .then((response) => response.json())
      .then((data) => {
        const a = document.createElement("a");
        a.href = data.url;
        a.download = fileKey.split("/").pop();
        document.body.appendChild(a);
        a.click();
        a.remove();
      })
      .catch((error) => {
        console.error("Error fetching pre-signed URL:", error);
      });
  };

  const getFileKeyFromUrl = (fileUrl) => {
    const parts = fileUrl.split(".com/");
    if (parts.length > 1) {
      return parts[1]; // Return the key after '.com/'
    }
    return null; // Return null if the URL is not in the expected format
  }

  return (
    <div>
      <section className="bg-blue-600 text-white text-center py-12">
        <h1 className="text-4xl font-semibold">
          Download Your Favorite Social Media Videos
        </h1>
        <p className="text-lg mt-4">
          Save videos from platforms like YouTube, Instagram, Facebook, and more
          with just a click!
        </p>
        <a href="#videoForm" className="bg-yellow-500 hover:bg-yellow-600 text-white px-6 py-3 rounded-md mt-6 inline-block">Start
          Downloading</a>
      </section>

      <div className="container mx-auto p-8">
        <h2 className="text-3xl font-bold text-gray-800 mb-6">
          Download YouTube Videos
        </h2>
        <p className="text-lg text-gray-600 mb-4">
          Enter the YouTube URL to download the video. You can also choose the
          segment length for downloading part of the video.
        </p>

        <form method="post" id="videoForm" className="mb-6">
          <input type="url" id="videoUrl" name="videoUrl" onKeyUp={
            (e) => {
              console.log(
                "Key pressed: " + e.target.value

              );
              
              setVideoUrl(e.target.value);
    
              }
          }  placeholder="Enter YouTube URL"
            className="w-full p-3 border border-gray-300 rounded-md mb-4" required />

          <label htmlFor="segmentLength" className="text-gray-700 font-medium">Segment Length (in seconds):</label>
          <input type="number" id="segmentLength" name="segmentLength" placeholder="e.g., 30"
            className="w-full p-3 border border-gray-300 rounded-md mb-6" min="1" required onKeyDown={
              (e) => {
                setSegmentLength(e.target.value);

              }
            } />

          <button type="button" onClick={processVideo}
            className="w-full bg-blue-600 text-white py-3 rounded-md hover:bg-blue-700 transition duration-300">
            Download Video
          </button>
        </form>
        <div className="mt-6 space-y-4 flex   space-x-4 w-full justify-between">
          <h2 className="text-3xl font-bold text-gray-800 mb-6">
            <a href="#" className="text-blue-600 hover:text-blue-800">Processed Videos</a>
          </h2>
          <button
            onClick={handleDeleteSelected}
            className="bg-red-600 text-white px-6 py-3 rounded-lg hover:bg-red-700 mt-4 w-full md:w-auto mx-auto mb-4"
          >
            Delete Selected
          </button>
        </div>
        <ul id="videoList" className="mt-6 space-y-4 flex  flex-col  space-x-4 flex-wrap w-full">
          <ul id="Youtube" className="space-y-4">
            {videos.map((video) => (
              <li
                key={video.id}
                className="bg-white p-6 rounded-lg shadow-lg mb-4 relative flex flex-col w-4/12"
              >
    
                {video.video_url && (
                  <div>
                    <iframe
                      width="400"
                      height="345"
                      src={`https://www.youtube.com/embed/${video.video_url.split("youtu.be/")[1]}`}
                      frameBorder="0"
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen;"
                    ></iframe>
                  </div>
                )}
                {!video.video_url && (
                  <p>No video URL available</p>
                )}
                {video.segment_length && (
                  <p>Segment Length: {video.segment_length} seconds</p>
                )}
                <p>Created At: {video.created_at}</p>
                <div className="mt-2 flex items-center space-x-4">
                  <button
                    onClick={() => handleDeleteVideo(video.id)}
                    className="text-white bg-red-600 hover:bg-red-700 px-4 py-2 mt-2 rounded"
                  >
                    <i className="fa fa-trash-o"></i> Delete 
                  </button>
                  <button
                    onChange={() => handleToggleSelect(video.id)}
                    className="text-white bg-red-600 hover:bg-red-700 px-4 py-2 mt-2 rounded"
                  >
                    <i className="fa fa-trash-o"></i> select 
                  </button>

                  {video.file_urls && video.file_urls.length > 0 && (
                    <div className="flex flex-wrap space-y-6 text-sm">
                      <select
                        className="text-blue-500 py-3 px-4 rounded w-full"
                        onChange={(e) =>
                          e.target.value && downloadShort(e.target.value)
                        }
                      >
                        <option value="" disabled selected>
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
        </ul>
      </div>

      <section className="bg-gray-100 py-12">
        <div className="container mx-auto text-center">
          <h2 className="text-3xl font-bold text-gray-800 mb-6">
            Why Use SocialClipSaver?
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="bg-white p-6 rounded-lg shadow-lg">
              <h3 className="text-xl font-semibold mb-4">Fast & Easy</h3>
              <p className="text-gray-600">
                Download videos from multiple social media platforms quickly with
                no hassle.
              </p>
            </div>
            <div className="bg-white p-6 rounded-lg shadow-lg">
              <h3 className="text-xl font-semibold mb-4">High Quality</h3>
              <p className="text-gray-600">
                We ensure high-quality video downloads with multiple formats
                available.
              </p>
            </div>
            <div className="bg-white p-6 rounded-lg shadow-lg">
              <h3 className="text-xl font-semibold mb-4">Free to Use</h3>
              <p className="text-gray-600">
                No charges, no sign-up required. Simply paste a URL and download.
              </p>
            </div>
          </div>
        </div>
      </section>
     
    </div>
  );
};

export default Youtube;
