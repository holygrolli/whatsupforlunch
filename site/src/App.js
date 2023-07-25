import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { solid } from '@fortawesome/fontawesome-svg-core/import.macro'

function LocationDetails({details}) {
  if (details.length === 0) {
    return null;
  }
  return (
    <label>
      | <FontAwesomeIcon icon={solid("circle-info")} style={{color: "#000000",}} /> {details.join(", ")}
    </label>
  )
}
function VersionInfo() {
  return (
    <div>Version {process.env.REACT_APP_VERSION ? process.env.REACT_APP_VERSION : "SNAPSHOT"}</div>
  )
}

function App() {
  const [data, setData] = useState([]);
  const [filteredData, setFilteredData] = useState([]); // Set initial state to an empty array
  const [selectedDate, setSelectedDate] = useState('');

  useEffect(() => {
    // Fetch data from the JSON file
    axios.get('./data.json').then((response) => {
      setData(response.data.locations);
    });
  }, []);

  const handleDateChange = (event) => {
    setSelectedDate(event.target.value);
  };
  useEffect(() => {
    // Function to get the current date in "YYYY-MM-DD" format
    const getCurrentDate = () => {
      const today = new Date();
      const year = today.getFullYear();
      const month = String(today.getMonth() + 1).padStart(2, '0');
      const day = String(today.getDate()).padStart(2, '0');
      return `${year}-${month}-${day}`;
    };

    // Set the selectedDate to the current date when the component mounts
    setSelectedDate(getCurrentDate());
  }, []); // Empty dependency array to ensure the effect runs only once, on mount

  useEffect(() => {
    // Filter data based on selectedDate
    if (selectedDate) {
      const transformedArray = [];
      for (const location of data) {
        const offers = location.offers;
        const locationCopy = { name: location.name, meals: [], details: location.details, link: location.link };
        for (const date in offers) {
          if (date === selectedDate) {
              locationCopy.meals = offers[date];
          }
        }
        transformedArray.push(locationCopy);
      }
      setFilteredData(transformedArray);
    } else {
      setFilteredData([]); // Set filteredData to an empty array when no date is selected
    }
  }, [selectedDate, data]);

  return (
    <div className="container">
      <h1>What's up for lunch?</h1>
      <label>
        Datum auswählen:&nbsp;
        <input type="date" value={selectedDate} onChange={handleDateChange} />
      </label>
      {filteredData.map((location, index) => (
      <div key={location.name} className="mt-3 p-2 border border-dark rounded">
        <h2>{location.name}</h2>
        <div><a href={location.link}><FontAwesomeIcon icon={solid("link")} style={{color: "#000000",}} /></a> <LocationDetails details={location.details} />
        </div>
        {location.meals.length > 0 &&
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th style={{width: 100 + 'px'}}>Preis</th>
            </tr>
          </thead>
          <tbody>
          {location.meals.map((meal,index) => {
            return (
            <tr key={meal.desc}>
              <td>{meal.desc}</td>
              <td>{meal.price}</td>
            </tr>
            )
          })}
          </tbody>
        </table>
        }
      </div>
      ))}
      <VersionInfo />
    </div>
  );
}

export default App;
