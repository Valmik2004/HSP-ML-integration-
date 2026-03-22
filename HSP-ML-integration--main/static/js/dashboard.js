// dashboard.js
document.addEventListener('DOMContentLoaded', () => {
    // --- Dashboard Elements ---
    const tempValue = document.getElementById('tempValue');
    const humidityValue = document.getElementById('humidityValue');
    const waterLevelValue = document.getElementById('waterLevelValue');
    const ldrValue = document.getElementById('ldrValue');
    const lastUpdated = document.getElementById('lastUpdated');
    const systemStatusSpan = document.getElementById('systemStatus');
    const currentPumpStateElement = document.getElementById('currentPumpState'); // New element
    const pumpLogTableBody = document.getElementById('pumpLogTableBody');

    // --- Chart Instances ---
    let waterLevelChart;
    let ldrChart;

    // --- Fetch Latest Sensor Data & System Status ---
    async function fetchLatestSensorData() {
        try {
            const response = await fetch('/api/latest_sensor_data');
            if (!response.ok) {
                if (response.status === 401) {
                    console.warn("Session expired or unauthorized. Redirecting to login.");
                    window.location.href = '/login';
                    return;
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();

            // Update sensor values
            tempValue.textContent = data.dhule_temperature_C !== 'N/A' ? `${data.dhule_temperature_C} °C` : 'N/A °C';
            humidityValue.textContent = data.dhule_humidity_perc !== 'N/A' ? `${data.dhule_humidity_perc} %` : 'N/A %';
            waterLevelValue.textContent = data.water_level !== 'N/A' ? `${data.water_level} raw` : 'N/A';
            ldrValue.textContent = data.ldr_value !== 'N/A' ? `${data.ldr_value} raw` : 'N/A';
            lastUpdated.textContent = data.timestamp !== 'N/A' ? data.timestamp : 'N/A';

            // Update system status
            if (data.system_online) {
                systemStatusSpan.textContent = 'System Status: Online';
                systemStatusSpan.className = 'px-3 py-1 rounded-full text-sm font-semibold text-white bg-green-500';
            } else {
                systemStatusSpan.textContent = 'System Status: Offline';
                systemStatusSpan.className = 'px-3 py-1 rounded-full text-sm font-semibold text-white bg-red-500';
            }

            // Update current pump state
            if (data.current_pump_state !== undefined) {
                currentPumpStateElement.textContent = data.current_pump_state === 1 ? 'ON' : 'OFF';
                currentPumpStateElement.className = `text-3xl font-bold ${data.current_pump_state === 1 ? 'text-green-600' : 'text-red-600'}`;
            } else {
                currentPumpStateElement.textContent = 'N/A';
                currentPumpStateElement.className = 'text-3xl font-bold text-gray-500';
            }


            console.log("Latest sensor data and system status updated.");

        } catch (error) {
            console.error('Error fetching latest sensor data:', error);
            systemStatusSpan.textContent = 'System Status: Error';
            systemStatusSpan.className = 'px-3 py-1 rounded-full text-sm font-semibold text-white bg-gray-500';
            currentPumpStateElement.textContent = 'Error';
            currentPumpStateElement.className = 'text-3xl font-bold text-red-600';
        }
    }

    // --- Fetch and Render Historical Charts ---
    async function fetchAndRenderCharts(period = '24h') {
        try {
            const response = await fetch(`/api/sensor_data_history?period=${period}`);
            if (!response.ok) {
                if (response.status === 401) {
                    console.warn("Session expired or unauthorized. Redirecting to login.");
                    window.location.href = '/login';
                    return;
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();

            // Use the 'timestamp_js' field from the backend, which is ISO formatted 'received_at'
            const timestamps = data.map(d => new Date(d.timestamp_js));
            const waterLevels = data.map(d => d.water_level);
            const ldrValues = data.map(d => d.ldr_value);

            // Destroy existing charts if they exist
            if (waterLevelChart) {
                waterLevelChart.destroy();
            }
            if (ldrChart) {
                ldrChart.destroy();
            }

            // Chart.js Time Scale Configuration
            const timeScaleConfig = {
                type: 'time',
                time: {
                    unit: 'hour', // Default to hour
                    tooltipFormat: 'MMM dd, HH:mm', // Format for tooltips
                    displayFormats: {
                        hour: 'HH:mm',
                        day: 'MMM dd'
                    }
                },
                title: {
                    display: true,
                    text: 'Time (IST)'
                },
                // Adaptive unit based on period
                adapters: {
                    date: {} // Required for Chart.js v3+ and time adapter
                }
            };

            if (period === '7d') {
                timeScaleConfig.time.unit = 'day';
            } else if (period === '12h' || period === '24h') {
                timeScaleConfig.time.unit = 'hour';
            }


            // Render Water Level Chart
            const waterLevelCtx = document.getElementById('waterLevelChart').getContext('2d');
            waterLevelChart = new Chart(waterLevelCtx, {
                type: 'line',
                data: {
                    labels: timestamps,
                    datasets: [{
                        label: 'Water Level (raw)',
                        data: waterLevels,
                        borderColor: 'rgb(75, 192, 192)',
                        tension: 0.1,
                        fill: false
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false, // Allows chart to fill container
                    scales: {
                        x: timeScaleConfig,
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Water Level (raw)'
                            }
                        }
                    },
                    plugins: {
                        tooltip: {
                            callbacks: {
                                title: function(context) {
                                    // context[0].label already formatted by time scale adapter
                                    return context[0].label;
                                }
                            }
                        }
                    }
                }
            });

            // Render LDR Chart
            const ldrCtx = document.getElementById('ldrChart').getContext('2d');
            ldrChart = new Chart(ldrCtx, {
                type: 'line',
                data: {
                    labels: timestamps,
                    datasets: [{
                        label: 'LDR Reading (raw)',
                        data: ldrValues,
                        borderColor: 'rgb(255, 205, 86)',
                        tension: 0.1,
                        fill: false
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { ...timeScaleConfig }, // Clone to avoid mutation side effects
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'LDR Reading (raw)'
                            }
                        }
                    },
                     plugins: {
                        tooltip: {
                            callbacks: {
                                title: function(context) {
                                    return context[0].label;
                                }
                            }
                        }
                    }
                }
            });

            console.log(`Charts updated for ${period} period.`);

        } catch (error) {
            console.error('Error fetching historical sensor data:', error);
            // Optionally, display an error message on the dashboard
        }
    }

    // --- Fetch Pump Logs ---
    async function fetchPumpLogs() {
        try {
            const response = await fetch('/api/pump_logs');
            if (!response.ok) {
                if (response.status === 401) {
                    console.warn("Session expired or unauthorized. Redirecting to login.");
                    // window.location.href = '/login'; // Already handled by fetchLatestSensorData, avoid multiple redirects
                    return;
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const logs = await response.json();

            pumpLogTableBody.innerHTML = ''; // Clear previous logs
            if (logs.length === 0) {
                pumpLogTableBody.innerHTML = '<tr><td colspan="4" class="py-3 px-6 text-center text-gray-500">No pump logs available.</td></tr>';
                return;
            }

            logs.forEach(log => {
                const row = document.createElement('tr');
                row.className = 'border-b border-gray-200 hover:bg-gray-50';
                row.innerHTML = `
                    <td class="py-3 px-6 text-left">${log.timestamp}</td>
                    <td class="py-3 px-6 text-left">
                        <span class="px-3 py-1 rounded-full text-xs font-semibold ${log.pump_state == 1 ? 'bg-green-200 text-green-800' : 'bg-red-200 text-red-800'}">
                            ${log.pump_state == 1 ? 'ON' : 'OFF'}
                        </span>
                    </td>
                    <td class="py-3 px-6 text-left">${log.reason}</td>
                    <td class="py-3 px-6 text-left">${log.duration}</td>
                `;
                pumpLogTableBody.appendChild(row);
            });
            console.log("Pump logs updated.");

        } catch (error) {
            console.error('Error fetching pump logs:', error);
        }
    }

    // --- ML Prediction Forms Handlers ---

    // Generic function to handle prediction form submissions (for forms with manual inputs)
    async function handleFormPrediction(formId, apiEndpoint, resultElementId, callback) {
        const form = document.getElementById(formId);
        const resultElement = document.getElementById(resultElementId);

        if (form) {
            form.addEventListener('submit', async (event) => {
                event.preventDefault();
                resultElement.textContent = 'Predicting...';
                resultElement.className = 'mt-4 text-xl font-bold text-center text-gray-600';

                const formData = new FormData(form);
                const payload = {};
                for (let [key, value] of formData.entries()) {
                    payload[key] = isNaN(Number(value)) ? value : Number(value); // Convert to number if numeric
                }
                
                await sendPredictionRequest(apiEndpoint, payload, resultElement, callback);
            });
        }
    }

    // Function to handle button-triggered predictions (where inputs are auto-filled)
    async function handleButtonPrediction(buttonId, apiEndpoint, resultElementId, callback) {
        const button = document.getElementById(buttonId);
        const resultElement = document.getElementById(resultElementId);

        if (button) {
            button.addEventListener('click', async () => {
                resultElement.textContent = 'Predicting...';
                resultElement.className = 'mt-4 text-xl font-bold text-center text-gray-600';
                
                // No specific payload needed from UI for pump prediction, backend fetches current data
                await sendPredictionRequest(apiEndpoint, {}, resultElement, callback);
            });
        }
    }

    // Central function to send prediction requests
    async function sendPredictionRequest(apiEndpoint, payload, resultElement, callback) {
        try {
            const response = await fetch(apiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                if (response.status === 401) {
                    console.warn("Session expired or unauthorized. Redirecting to login.");
                    window.location.href = '/login';
                    return;
                }
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (callback) {
                callback(data, resultElement);
            }
        } catch (error) {
            console.error(`Error during prediction from ${apiEndpoint}:`, error);
            resultElement.textContent = `Error: ${error.message}`;
            resultElement.className = 'mt-4 text-xl font-bold text-center text-red-600';
        }
    }


    // Callbacks for each prediction type
    function displayYieldResult(data, resultElement) {
        if (data.yield_grams !== undefined) {
            resultElement.textContent = `Predicted Yield: ${data.yield_grams.toFixed(2)} grams`;
            resultElement.className = 'mt-4 text-xl font-bold text-center text-pink-700';
        } else {
            resultElement.textContent = 'Prediction failed or no yield data.';
            resultElement.className = 'mt-4 text-xl font-bold text-center text-red-600';
        }
    }

    function displayPumpResult(data, resultElement) {
        if (data.pump_action !== undefined) {
            const pumpStatus = data.pump_action === 1 ? 'ON' : 'OFF';
            resultElement.textContent = `Predicted Pump Action: ${pumpStatus}`;
            resultElement.className = `mt-4 text-xl font-bold text-center ${data.pump_action === 1 ? 'text-blue-700' : 'text-gray-700'}`;
            if (data.pump_action === 1) {
                 // Trigger a refresh of pump logs and latest sensor data (for pump state)
                setTimeout(() => {
                    fetchPumpLogs();
                    fetchLatestSensorData(); // To update the pump state display immediately
                }, 2000); // Give a small delay for MQTT message to process and log
            }
        } else {
            resultElement.textContent = 'Prediction failed or no pump action data.';
            resultElement.className = 'mt-4 text-xl font-bold text-center text-red-600';
        }
    }

    function displayAnomalyResult(data, resultElement) {
        if (data.anomaly_flag !== undefined) {
            const anomalyStatus = data.anomaly_flag === 1 ? 'Anomaly Detected!' : 'No Anomaly Detected';
            resultElement.textContent = `Anomaly Check: ${anomalyStatus}`;
            resultElement.className = `mt-4 text-xl font-bold text-center ${data.anomaly_flag === 1 ? 'text-red-700' : 'text-green-700'}`;
        } else {
            resultElement.textContent = 'Prediction failed or no anomaly data.';
            resultElement.className = 'mt-4 text-xl font-bold text-center text-red-600';
        }
    }

    function displayHarvestResult(data, resultElement) {
        if (data.harvest_time_hours !== undefined) {
            const days = Math.floor(data.harvest_time_hours / 24);
            const hours = Math.round(data.harvest_time_hours % 24);
            resultElement.textContent = `Predicted Harvest Time: ${days} days, ${hours} hours`;
            resultElement.className = 'mt-4 text-xl font-bold text-center text-green-700';
        } else {
            resultElement.textContent = 'Prediction failed or no harvest data.';
            resultElement.className = 'mt-4 text-xl font-bold text-center text-red-600';
        }
    }

    // Initialize all prediction forms and buttons
    handleFormPrediction('yieldPredictForm', '/api/predict_yield', 'yieldResult', displayYieldResult);
    handleButtonPrediction('predictPumpBtn', '/api/predict_pump', 'pumpResult', displayPumpResult); // Button for pump prediction
    handleFormPrediction('anomalyPredictForm', '/api/predict_anomaly', 'anomalyResult', displayAnomalyResult);
    handleFormPrediction('harvestPredictForm', '/api/predict_harvest', 'harvestResult', displayHarvestResult);


    // --- Event Listeners ---
    // Period buttons for charts
    document.querySelectorAll('.period-btn').forEach(button => {
        button.addEventListener('click', (event) => {
            // Remove active class from all buttons
            document.querySelectorAll('.period-btn').forEach(btn => {
                btn.classList.remove('bg-blue-500', 'text-white');
                btn.classList.add('bg-gray-200', 'text-gray-800');
            });
            // Add active class to clicked button
            event.target.classList.add('bg-blue-500', 'text-white');
            event.target.classList.remove('bg-gray-200', 'text-gray-800');

            const period = event.target.dataset.period;
            fetchAndRenderCharts(period);
        });
    });

    // --- Initial Load and Periodic Updates ---
    fetchLatestSensorData();
    fetchAndRenderCharts('24h'); // Default to 24 hours chart
    fetchPumpLogs();

    // Set intervals for periodic updates
    setInterval(fetchLatestSensorData, 30000); // Update current readings and status every 30 seconds
    setInterval(fetchPumpLogs, 60000); // Update pump logs every minute
    // Charts are updated only when period button is clicked, or on page load.
    // You can add an interval here to auto-update charts as well if desired.
    // setInterval(() => fetchAndRenderCharts(document.querySelector('.period-btn.bg-blue-500')?.dataset.period || '24h'), 5 * 60 * 1000); // Every 5 minutes
});
