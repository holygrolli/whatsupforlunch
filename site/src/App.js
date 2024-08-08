import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { solid } from '@fortawesome/fontawesome-svg-core/import.macro'
import { getWeek } from 'date-fns';

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
  const ver = process.env.REACT_APP_VERSION ? process.env.REACT_APP_VERSION : "SNAPSHOT";
  const hash = process.env.REACT_APP_HASH ? process.env.REACT_APP_HASH : "main";
  return (
    <div className='text-center small'>Release <a href={"https://github.com/holygrolli/whatsupforlunch/releases/tag/"+ ver}>{ver}</a> | Source: <a href={"https://github.com/holygrolli/whatsupforlunch/commit/"+hash}>{hash}</a> </div>
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
      // determine current calendar week in format YYYY-WW based on selectedDate
      let selectedDateObj = new Date(selectedDate);
      // Get the day of the week (0 - Sunday, 1 - Monday, ..., 6 - Saturday)
      let dayOfWeek = selectedDateObj.getDay();

      // Calculate how many days to go back to get to the previous Monday
      let daysToMonday = (dayOfWeek === 0) ? 6 : dayOfWeek - 1; // If it's Sunday, go back 6 days

      // Create a new date object for the previous Monday
      let mondayDateObj = new Date(selectedDateObj);
      mondayDateObj.setDate(selectedDateObj.getDate() - daysToMonday);

      // Calculate the year and week number based on the Monday date
      let selectedYear = mondayDateObj.getFullYear();

      // Calculate the week number based on the Monday date
      let selectedWeek = String(getWeek(mondayDateObj, {
        weekStartsOn: 1, firstWeekContainsDate: 4})).padStart(2, '0');
      // Create the selected week string
      let selectedWeekString = `${selectedYear}-W${selectedWeek}`;

      const transformedArray = [];
      for (const location of data) {
        const offers = location.offers;
        const locationCopy = { name: location.name, meals: { day: [], week: []}, details: location.details, link: location.link };
        for (const date in offers) {
          if (date === selectedDate) {
              locationCopy.meals.day = offers[date];
          }
          if (date === selectedWeekString) {
              locationCopy.meals.week = offers[date];
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
        {(location.meals.day.length > 0 || location.meals.week.length > 0) &&
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th style={{width: 100 + 'px'}}>Preis</th>
            </tr>
          </thead>
          <tbody>
          {location.meals.day.length > 0 && location.meals.week.length > 0 &&
          <tr>
            <td colSpan="2" className="text-left fw-bold">Tagesangebot</td>
          </tr>
          }
          {location.meals.day.map((meal,index) => {
            return (
            <tr key={meal.desc}>
              <td>{meal.desc}</td>
              <td>{meal.price}</td>
            </tr>
            )
          })}
          {location.meals.day.length > 0 && location.meals.week.length > 0 &&
          <tr>
            <td colSpan="2" className="text-left fw-bold">Wochenangebot</td>
          </tr>
          }
          {location.meals.week.map((meal,index) => {
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
      <div className='pt-1'>
        <VersionInfo />
      </div>
    </div>
  );
}

export default App;
