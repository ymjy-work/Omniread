package com.omniread.admin;

import java.util.List;

import com.omniread.admin.model.AdminUserCreateDTO;
import com.omniread.admin.model.AdminUserVO;
import com.omniread.admin.model.BalanceGrantDTO;
import com.omniread.auth.AuthMapper;
import com.omniread.auth.model.UserEntity;
import com.omniread.billing.LedgerMapper;
import com.omniread.billing.PlanCatalogMapper;
import com.omniread.common.BusinessException;
import com.omniread.common.ErrorCode;
import com.omniread.common.Timestamps;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AdminService {

	private static final double INITIAL_BALANCE = 20;

	private final AuthMapper authMapper;
	private final LedgerMapper ledgerMapper;
	private final PlanCatalogMapper planCatalogMapper;

	public AdminService(AuthMapper authMapper, LedgerMapper ledgerMapper,
			PlanCatalogMapper planCatalogMapper) {
		this.authMapper = authMapper;
		this.ledgerMapper = ledgerMapper;
		this.planCatalogMapper = planCatalogMapper;
	}

	@Transactional
	public AdminUserVO createUser(AdminUserCreateDTO request) {
		if (authMapper.findUserByUsername(request.username()) != null) {
			throw new BusinessException(ErrorCode.BAD_REQUEST, "用户名已存在");
		}
		String now = Timestamps.now();
		UserEntity user = new UserEntity();
		user.setUsername(request.username());
		user.setPasswordHash(new BCryptPasswordEncoder().encode(request.password()));
		user.setDisplayName(request.displayName() == null || request.displayName().isBlank()
				? request.username() : request.displayName());
		user.setCreatedAt(now);
		user.setRole("user");
		user.setPlan("free");
		user.setCredits(100L);
		user.setPlanStartedAt(now);
		user.setPlanExpiresAt(Timestamps.plusDays(now,
				planCatalogMapper.findByCode("free").getDurationDays()));
		user.setBalance(INITIAL_BALANCE);
		authMapper.insertUser(user);
		ledgerMapper.insertBalance(user.getId(), "grant", INITIAL_BALANCE, INITIAL_BALANCE, "初始余额", now);
		ledgerMapper.insertCredit(user.getId(), "init", 100, 100, "初始积分", now);
		return AdminUserVO.of(user);
	}

	public List<AdminUserVO> listUsers() {
		return authMapper.findAllUsers().stream().map(AdminUserVO::of).toList();
	}

	@Transactional
	public AdminUserVO grantBalance(long userId, BalanceGrantDTO request) {
		UserEntity user = authMapper.findUserById(userId);
		if (user == null) {
			throw new BusinessException(ErrorCode.NOT_FOUND, "用户不存在");
		}
		authMapper.addBalance(userId, request.amount());
		double balanceAfter = user.getBalance() + request.amount();
		ledgerMapper.insertBalance(userId, "grant", request.amount(), balanceAfter,
				request.reason(), Timestamps.now());
		user.setBalance(balanceAfter);
		return AdminUserVO.of(user);
	}
}
