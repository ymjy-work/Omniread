package com.omniread.auth.model;

/** user 表行。 */
public class UserEntity {

	private Long id;
	private String username;
	private String passwordHash;
	private String displayName;
	private String createdAt;
	private String role;
	private String plan;
	private Long credits;
	private String planStartedAt;
	private String planExpiresAt;
	private Double balance;

	public Long getId() {
		return id;
	}

	public void setId(Long id) {
		this.id = id;
	}

	public String getUsername() {
		return username;
	}

	public void setUsername(String username) {
		this.username = username;
	}

	public String getPasswordHash() {
		return passwordHash;
	}

	public void setPasswordHash(String passwordHash) {
		this.passwordHash = passwordHash;
	}

	public String getDisplayName() {
		return displayName;
	}

	public void setDisplayName(String displayName) {
		this.displayName = displayName;
	}

	public String getCreatedAt() {
		return createdAt;
	}

	public void setCreatedAt(String createdAt) {
		this.createdAt = createdAt;
	}

	public String getRole() {
		return role;
	}

	public void setRole(String role) {
		this.role = role;
	}

	public String getPlan() {
		return plan;
	}

	public void setPlan(String plan) {
		this.plan = plan;
	}

	public Long getCredits() {
		return credits;
	}

	public void setCredits(Long credits) {
		this.credits = credits;
	}

	public String getPlanStartedAt() {
		return planStartedAt;
	}

	public void setPlanStartedAt(String planStartedAt) {
		this.planStartedAt = planStartedAt;
	}

	public String getPlanExpiresAt() {
		return planExpiresAt;
	}

	public void setPlanExpiresAt(String planExpiresAt) {
		this.planExpiresAt = planExpiresAt;
	}

	public Double getBalance() {
		return balance;
	}

	public void setBalance(Double balance) {
		this.balance = balance;
	}
}
