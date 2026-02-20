-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Generation Time: Feb 19, 2026 at 11:57 AM
-- Server version: 10.4.32-MariaDB
-- PHP Version: 8.2.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `triplit`
--

-- --------------------------------------------------------

--
-- Table structure for table `locations`
--

CREATE TABLE `locations` (
  `location_id` int(11) NOT NULL,
  `name` varchar(200) NOT NULL,
  `locality` varchar(120) DEFAULT NULL,
  `region` varchar(120) DEFAULT NULL,
  `category` varchar(50) DEFAULT NULL,
  `latitude` double DEFAULT NULL,
  `longitude` double DEFAULT NULL,
  `image_url` text DEFAULT NULL,
  `description` text DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `trips`
--

CREATE TABLE `trips` (
  `trip_id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `trip_name` varchar(150) NOT NULL,
  `start_region` varchar(100) NOT NULL,
  `end_region` varchar(100) DEFAULT NULL,
  `focus_mode` text DEFAULT NULL,
  `diversity_mode` tinyint(1) DEFAULT 0,
  `pace` varchar(20) NOT NULL,
  `companion_type` varchar(20) DEFAULT NULL,
  `season` varchar(20) DEFAULT NULL,
  `planning_mode` varchar(20) NOT NULL,
  `trip_status` varchar(20) DEFAULT 'draft',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `trip_days` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `trip_locations`
--

CREATE TABLE `trip_locations` (
  `trip_location_id` int(11) NOT NULL,
  `trip_id` int(11) NOT NULL,
  `location_id` int(11) NOT NULL,
  `status` varchar(20) NOT NULL DEFAULT 'suggested',
  `visit_order` int(11) DEFAULT NULL,
  `added_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `trip_regions`
--

CREATE TABLE `trip_regions` (
  `trip_region_id` int(11) NOT NULL,
  `trip_id` int(11) NOT NULL,
  `region_name` varchar(120) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `trip_route_plan`
--

CREATE TABLE `trip_route_plan` (
  `plan_id` int(11) NOT NULL,
  `trip_id` int(11) NOT NULL,
  `region` varchar(120) NOT NULL,
  `optimized_order_json` text NOT NULL,
  `total_distance_km` double DEFAULT NULL,
  `total_duration_min` double DEFAULT NULL,
  `last_updated` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `trip_route_segments`
--

CREATE TABLE `trip_route_segments` (
  `segment_id` int(11) NOT NULL,
  `trip_id` int(11) NOT NULL,
  `region` varchar(120) NOT NULL,
  `from_location_id` int(11) NOT NULL,
  `to_location_id` int(11) NOT NULL,
  `distance_km` double NOT NULL,
  `duration_min` double NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `users`
--

CREATE TABLE `users` (
  `user_id` int(11) NOT NULL,
  `full_name` varchar(100) NOT NULL,
  `email` varchar(150) NOT NULL,
  `password_hash` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `wishlist`
--

CREATE TABLE `wishlist` (
  `wishlist_id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `location_id` int(11) NOT NULL,
  `added_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Indexes for dumped tables
--

--
-- Indexes for table `locations`
--
ALTER TABLE `locations`
  ADD PRIMARY KEY (`location_id`),
  ADD KEY `idx_locations_name` (`name`),
  ADD KEY `idx_locations_region` (`region`),
  ADD KEY `idx_locations_category` (`category`);

--
-- Indexes for table `trips`
--
ALTER TABLE `trips`
  ADD PRIMARY KEY (`trip_id`),
  ADD KEY `fk_trip_user` (`user_id`);

--
-- Indexes for table `trip_locations`
--
ALTER TABLE `trip_locations`
  ADD PRIMARY KEY (`trip_location_id`),
  ADD UNIQUE KEY `uq_trip_location` (`trip_id`,`location_id`),
  ADD KEY `fk_tl_trip` (`trip_id`),
  ADD KEY `fk_tl_location` (`location_id`);

--
-- Indexes for table `trip_regions`
--
ALTER TABLE `trip_regions`
  ADD PRIMARY KEY (`trip_region_id`),
  ADD KEY `trip_id` (`trip_id`);

--
-- Indexes for table `trip_route_plan`
--
ALTER TABLE `trip_route_plan`
  ADD PRIMARY KEY (`plan_id`),
  ADD KEY `fk_plan_trip` (`trip_id`),
  ADD KEY `idx_plan_trip_region` (`trip_id`,`region`);

--
-- Indexes for table `trip_route_segments`
--
ALTER TABLE `trip_route_segments`
  ADD PRIMARY KEY (`segment_id`),
  ADD KEY `fk_segment_trip` (`trip_id`),
  ADD KEY `fk_segment_from` (`from_location_id`),
  ADD KEY `fk_segment_to` (`to_location_id`),
  ADD KEY `idx_segments_trip_region` (`trip_id`,`region`);

--
-- Indexes for table `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`user_id`),
  ADD UNIQUE KEY `email` (`email`);

--
-- Indexes for table `wishlist`
--
ALTER TABLE `wishlist`
  ADD PRIMARY KEY (`wishlist_id`),
  ADD UNIQUE KEY `uq_wishlist` (`user_id`,`location_id`),
  ADD KEY `location_id` (`location_id`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `locations`
--
ALTER TABLE `locations`
  MODIFY `location_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `trips`
--
ALTER TABLE `trips`
  MODIFY `trip_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `trip_locations`
--
ALTER TABLE `trip_locations`
  MODIFY `trip_location_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `trip_regions`
--
ALTER TABLE `trip_regions`
  MODIFY `trip_region_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `trip_route_plan`
--
ALTER TABLE `trip_route_plan`
  MODIFY `plan_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `trip_route_segments`
--
ALTER TABLE `trip_route_segments`
  MODIFY `segment_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `users`
--
ALTER TABLE `users`
  MODIFY `user_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `wishlist`
--
ALTER TABLE `wishlist`
  MODIFY `wishlist_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `trips`
--
ALTER TABLE `trips`
  ADD CONSTRAINT `fk_trip_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE;

--
-- Constraints for table `trip_locations`
--
ALTER TABLE `trip_locations`
  ADD CONSTRAINT `fk_tl_location` FOREIGN KEY (`location_id`) REFERENCES `locations` (`location_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_tl_trip` FOREIGN KEY (`trip_id`) REFERENCES `trips` (`trip_id`) ON DELETE CASCADE;

--
-- Constraints for table `trip_regions`
--
ALTER TABLE `trip_regions`
  ADD CONSTRAINT `trip_regions_ibfk_1` FOREIGN KEY (`trip_id`) REFERENCES `trips` (`trip_id`) ON DELETE CASCADE;

--
-- Constraints for table `trip_route_plan`
--
ALTER TABLE `trip_route_plan`
  ADD CONSTRAINT `fk_plan_trip` FOREIGN KEY (`trip_id`) REFERENCES `trips` (`trip_id`) ON DELETE CASCADE;

--
-- Constraints for table `trip_route_segments`
--
ALTER TABLE `trip_route_segments`
  ADD CONSTRAINT `fk_segment_from` FOREIGN KEY (`from_location_id`) REFERENCES `locations` (`location_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_segment_to` FOREIGN KEY (`to_location_id`) REFERENCES `locations` (`location_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `fk_segment_trip` FOREIGN KEY (`trip_id`) REFERENCES `trips` (`trip_id`) ON DELETE CASCADE;

--
-- Constraints for table `wishlist`
--
ALTER TABLE `wishlist`
  ADD CONSTRAINT `wishlist_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `wishlist_ibfk_2` FOREIGN KEY (`location_id`) REFERENCES `locations` (`location_id`) ON DELETE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
