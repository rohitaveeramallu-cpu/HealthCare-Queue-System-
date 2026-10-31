CREATE DATABASE IF NOT EXISTS healthcare_queue;
USE healthcare_queue;

CREATE TABLE IF NOT EXISTS doctors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    dept VARCHAR(100) NOT NULL,
    avg_time INT NOT NULL DEFAULT 10,
    available BOOLEAN DEFAULT TRUE,
    next_token_number INT DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    token_no VARCHAR(20) UNIQUE NOT NULL,
    patient_name VARCHAR(100) NOT NULL,
    age INT NOT NULL,
    phone VARCHAR(10) NOT NULL,
    doctor_id INT NOT NULL,
    patient_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'Waiting',
    registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    completed_at DATETIME NULL,
    FOREIGN KEY (doctor_id) REFERENCES doctors(id)
);

INSERT IGNORE INTO doctors (id,name,dept,avg_time,available)
VALUES
(1,'Dr. Sharma','General Medicine',10,TRUE),
(2,'Dr. Reddy','Pediatrics',15,TRUE),
(3,'Dr. Khan','Orthopedics',20,FALSE);